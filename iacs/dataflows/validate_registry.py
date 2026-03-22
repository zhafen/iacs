"""This module validates the data in the registry against their schema and coerces or
warns as appropriate.
"""

import ast
import re

import pandas as pd
import pandera.ibis as pa
from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from ..registry import Registry
from ..utils import dhash


_ENTITY_PATH_PATTERN = re.compile(r"^(.+?)\[\d+\]\..+$")


@extract_fields(dict(entity_id=ir.Table, parent=ir.Table, field=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in a registry."""

    return registry._components


def updated_parent(entity_id: ir.Table, parent: ir.Table) -> ir.Table:
    """Convert the entity paths in entity_id_table into parent-child relationships and
    add them to the parent component.

    Produces two kinds of parent-child rows:

    1. **Hierarchy-implied**: every nested entity (whose entity path contains
       a dot after the file-id separator) is a child of the entity at the
       path one level up.
    2. **Explicit**: rows in the ``parent`` component table declare a parent
       via a string reference (``value``), which is resolved to an
       ``entity_id`` by matching against ``entity_key`` in the entity_id_table.

    Parameters
    ----------
    entity_id : ir.Table
        One row per entity with columns ``hash``, ``path``, ``entity_key``, ``filepath``.
    parent : ir.Table
        The ``parent`` component table from the registry, containing at
        minimum ``entity_id`` and ``value`` (the string reference to the
        parent entity).

    Returns
    -------
    ir.Table
        A table with columns ``entity_id`` and ``parent_id``, each row
        representing a child→parent relationship as hashed entity IDs.
    """
    df_spine = entity_id.to_pandas()
    df_spine = df_spine.rename(columns={"value": "entity_id"})
    df_spine["entity_path"] = df_spine["path"]

    # ── Part 1: hierarchy-implied parents from entity path nesting ────────
    def has_parent(entity_path):
        sep = entity_path.find(":")
        name_part = entity_path[sep + 1:] if sep != -1 else entity_path
        return "." in name_part

    def get_parent_path(entity_path):
        sep = entity_path.find(":")
        if sep != -1:
            file_id, name_part = entity_path[:sep], entity_path[sep + 1:]
            return f"{file_id}:{name_part.rsplit('.', 1)[0]}"
        return entity_path.rsplit(".", 1)[0]

    spine_pairs = df_spine[["entity_id", "entity_path"]].dropna().drop_duplicates()
    nested = spine_pairs[spine_pairs["entity_path"].apply(has_parent)].copy()

    if nested.empty:
        hierarchy = pd.DataFrame([], columns=["entity_id", "parent_id"])
    else:
        nested["parent_id"] = nested["entity_path"].apply(
            lambda ep: dhash(get_parent_path(ep))
        )
        hierarchy = nested[["entity_id", "parent_id"]].drop_duplicates()

    # ── Part 2: explicit parent components ────────────────────────────────
    # Build entity_key → entity_id lookup from the spine.
    key_to_id = (
        df_spine[["entity_id", "entity_key"]]
        .dropna()
        .drop_duplicates(subset=["entity_id", "entity_key"])
        .drop_duplicates(subset=["entity_key"])  # keep first for ambiguous keys
        .set_index("entity_key")["entity_id"]
        .to_dict()
    )

    df_parent = parent.to_pandas()
    if not df_parent.empty and "value" in df_parent.columns:
        df_parent = df_parent[["entity_id", "value"]].dropna(subset=["value"])
        df_parent["parent_id"] = df_parent["value"].map(key_to_id)
        explicit = (
            df_parent[["entity_id", "parent_id"]]
            .dropna(subset=["parent_id"])
            .drop_duplicates()
        )
    else:
        explicit = pd.DataFrame([], columns=["entity_id", "parent_id"])

    combined = (
        pd.concat([hierarchy, explicit], ignore_index=True)
        .drop_duplicates()
        .reset_index(drop=True)
    )
    return ibis.memtable(combined)


_IACS_TO_PYTHON_TYPE: dict[str, type] = {
    "str": str,
    "bool": bool,
    "int": int,
    "float": float,
}


def _coerce_default(val, py_type: type):
    """Coerce a raw default value to the given Python type for use as an ibis literal."""
    if py_type is bool:
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes")
        return bool(val)
    try:
        return py_type(val)
    except (ValueError, TypeError):
        return val


def validated_field(field: ir.Table) -> ir.Table:
    """The ((field)) component contains the data for the schema for all components.
    This includes the ((field)) component itself. We will use the ((field)) component
    to validate the data in all components, but first we need to use the appropriate
    records in the ((field)) component to validate the data in just the ((field))
    component.

    The schema for ``field`` is defined by the entity
    ``builtins.components:data_structure.field``.  Each row with that
    ``entity_id`` declares a field name (``value`` column) and an expected type
    (``type`` column).  Those rows are materialised (they are a handful of
    records) to build a :class:`pandera.ibis.DataFrameSchema`; the schema is
    then applied to the full table lazily so the rest of the data never leaves
    the query engine.

    Parameters
    ----------
    field : ir.Table
        The raw ``field`` component table from the registry.

    Returns
    -------
    ir.Table
        A lazy ibis expression with type coercions applied for every column
        that has a known type in the ``data_structure.field`` schema.
    """
    field_entity_id = dhash("builtins.components:data_structure.field")

    # ── Materialise only the schema-defining rows (O(1) records) ──────────
    # We need these as Python objects to build the pandera schema.  The full
    # table is never pulled into memory.
    select_cols = [c for c in ("value", "type", "default") if c in field.columns]
    if "value" not in select_cols:
        return field

    schema_df = (
        field
        .filter(field["entity_id"] == field_entity_id)
        .select(select_cols)
        .execute()
    )

    type_map: dict[str, type] = {}
    default_map: dict[str, object] = {}
    for _, row in schema_df.iterrows():
        name = row.get("value")
        dtype = row.get("type")
        default_val = row.get("default")
        if pd.notna(name) and name:
            name = str(name)
            if pd.notna(dtype) and str(dtype) in _IACS_TO_PYTHON_TYPE:
                type_map[name] = _IACS_TO_PYTHON_TYPE[str(dtype)]
            if pd.notna(default_val):
                default_map[name] = default_val

    if not type_map and not default_map:
        return field

    existing = set(field.columns)
    original_existing = set(existing)
    _IBIS_DTYPE = {bool: "boolean", str: "string", int: "int64", float: "float64"}

    result = field

    # ── Add missing schema columns with null values ────────────────────────
    for col_name, col_type in type_map.items():
        if col_name not in existing:
            result = result.mutate(**{col_name: ibis.null().cast(_IBIS_DTYPE[col_type])})
            existing.add(col_name)

    # ── Cast typed columns first (raw data is all strings; cast before fill) ─
    # For bool columns from raw data we also convert "" → NULL first; DuckDB
    # raises on CAST('' AS BOOLEAN) but handles NULL cleanly.
    for col_name, col_type in type_map.items():
        if col_name not in existing:
            continue
        expr = result[col_name]
        if col_type is bool and col_name in original_existing:
            expr = expr.nullif("")
        result = result.mutate(**{col_name: expr.cast(_IBIS_DTYPE[col_type])})

    # ── Fill in schema defaults for null values (after casting so types match) ─
    for col_name, default_val in default_map.items():
        if col_name not in existing:
            continue
        col_type = type_map.get(col_name)
        if col_type is not None:
            lit = ibis.literal(_coerce_default(default_val, col_type)).cast(_IBIS_DTYPE[col_type])
        else:
            lit = ibis.literal(str(default_val))
        result = result.mutate(**{col_name: result[col_name].fill_null(lit)})

    # ── Validate with pandera (types now match; no coerce needed) ─────────
    columns = {
        col_name: pa.Column(col_type, nullable=True)
        for col_name, col_type in type_map.items()
        if col_name in existing
    }
    schema = pa.DataFrameSchema(columns)
    return schema.validate(result)


def derived_field(validated_field: ir.Table, updated_parent: ir.Table) -> ir.Table:
    """Component definitions inherit fields from their parents, but can override them.
    The derived_field table contains the results of applying this inheritance.

    For each entity the full set of fields is resolved by a BFS walk up the
    parent chain.  The child's own definition of a field always beats any
    ancestor's definition of a field with the same name (``value`` column).
    The output has the same columns as ``validated_field`` but one row per
    ``(entity_id, field_name)`` pair, where ``entity_id`` is the entity that
    *has* the field (directly or through inheritance).

    Parameters
    ----------
    validated_field : ir.Table
        The type-coerced field component table produced by ``validated_field``.
    updated_parent : ir.Table
        Parent–child relationships with columns ``entity_id`` and ``parent_id``.

    Returns
    -------
    ir.Table
        One row per (entity, field_name) with the winning field definition.
    """
    df_field = validated_field.execute()
    df_parent = updated_parent.execute()

    # ── entity_own_fields: entity_id -> {field_name: row_dict} ───────────
    entity_own_fields: dict[str, dict[str, dict]] = {}
    for _, row in df_field.iterrows():
        eid = row["entity_id"]
        fname = row.get("value")
        if pd.isna(fname) or not fname:
            continue
        entity_own_fields.setdefault(str(eid), {})[str(fname)] = row.to_dict()

    # ── parent_map: entity_id -> [parent_id, ...] ─────────────────────────
    parent_map: dict[str, list[str]] = {}
    for _, row in df_parent.iterrows():
        eid, pid = row.get("entity_id"), row.get("parent_id")
        if pd.notna(eid) and pd.notna(pid):
            parent_map.setdefault(str(eid), []).append(str(pid))

    # ── BFS resolver: child fields beat parent fields ─────────────────────
    def resolve_fields(start_id: str) -> dict[str, dict]:
        resolved: dict[str, dict] = {}
        visited: set[str] = set()
        queue = [start_id]
        while queue:
            eid = queue.pop(0)
            if eid in visited:
                continue
            visited.add(eid)
            for fname, frow in entity_own_fields.get(eid, {}).items():
                if fname not in resolved:
                    resolved[fname] = frow
            queue.extend(p for p in parent_map.get(eid, []) if p not in visited)
        return resolved

    # ── Emit one row per (entity, field_name) ─────────────────────────────
    all_entities = (
        set(entity_own_fields)
        | set(parent_map)
        | {p for parents in parent_map.values() for p in parents}
    )

    result_rows = []
    for entity_id in sorted(all_entities):
        own_fields = entity_own_fields.get(entity_id, {})
        own_field_names = set(own_fields)
        own_indices = [r.get("component_index", 0) for r in own_fields.values()]
        next_index = max(own_indices, default=0) + 1

        for fname, frow in resolve_fields(entity_id).items():
            if fname in own_field_names:
                result_rows.append({**frow, "entity_id": entity_id})
            else:
                result_rows.append(
                    {**frow, "entity_id": entity_id, "component_index": next_index}
                )
                next_index += 1

    if result_rows:
        result_df = (
            pd.DataFrame(result_rows)
            .drop_duplicates(subset=["entity_id", "value"])
            .reset_index(drop=True)
        )
    else:
        result_df = df_field.iloc[0:0].copy()

    return ibis.memtable(result_df)


def updated_components(
    updated_parent: ir.Table, derived_field: ir.Table, registry: Registry
) -> dict:
    """Return a copy of the registry's component dict with the two tables that
    were processed earlier in the DAG replaced by their updated versions.

    ``updated_parent`` has merged the hierarchy-implied parent rows with the
    explicit ones; ``derived_field`` has resolved field inheritance.  Both need
    to be visible to the rest of the pipeline before component-level validation
    begins.

    Parameters
    ----------
    updated_parent : ir.Table
        The merged parent-relationship table from ``updated_parent``.
    derived_field : ir.Table
        The inheritance-resolved field table from ``derived_field``.
    registry : Registry
        The registry whose components dict is used as the base.

    Returns
    -------
    dict
        A shallow copy of ``registry._components`` with ``"parent"`` replaced
        by ``updated_parent`` and ``"field"`` replaced by ``derived_field``.
    """
    components = dict(registry._components)
    components["parent"] = updated_parent
    components["field"] = derived_field
    return components

def _isnull(val) -> bool:
    """Return True if val represents a missing/null value."""
    if val is None:
        return True
    if isinstance(val, (list, dict)):
        return False
    try:
        result = pd.isna(val)
        return bool(result) if isinstance(result, (bool, type(result))) else False
    except (TypeError, ValueError):
        return False


def _parse_range(val):
    """Parse a range value into a list, handling string representations."""
    if isinstance(val, list):
        return val
    if _isnull(val):
        return None
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                pass
    return None


@unpack_fields("validated_components", "invalid_field")
def validated_data(
    updated_components: dict, derived_field: ir.Table, entity_id: ir.Table
) -> tuple[dict, ir.Table]:
    """Use the schemas defined by the ((field)) component to validate and coerce the data in each component.

    Follows the same pattern as ``validated_field``: materialise only the
    schema-defining rows (O(fields) records per component type), build ibis
    mutate chains for column addition, type casting, and default filling, then
    validate types with :mod:`pandera.ibis`.  Constraint violations (nullable,
    categorical range) are collected as ibis filter sub-queries and unioned
    into ``invalid_field`` without pulling component data into memory.

    Parameters
    ----------
    updated_components : dict
        Dict of component_type -> ibis Table (from ``updated_components``).
    derived_field : ir.Table
        Inheritance-resolved field definitions (from ``derived_field``).
    entity_id : ir.Table
        One row per entity (hash, path, value, alias, entity_key, filepath),
        used to map entity_key -> entity_id for schema lookup.

    Returns
    -------
    tuple[dict, ir.Table]
        ``(validated_components, invalid_field)`` where ``validated_components``
        is a dict of component_type -> coerced ibis Table, and ``invalid_field``
        is an ibis Table of rows that failed nullable or range constraints.
    """
    _IBIS_DTYPE = {bool: "boolean", str: "string", int: "int64", float: "float64"}

    # ── 1. Materialise schema rows (small) and build entity_key -> ids ─────
    df_derived = derived_field.execute()
    schema_entity_ids = set(df_derived["entity_id"].dropna().astype(str))

    key_to_schema_ids: dict[str, list[str]] = {}
    df_spine = entity_id.execute()
    df_spine = df_spine.rename(columns={"value": "entity_id"})
    if {"entity_id", "entity_key"}.issubset(df_spine.columns):
        for _, row in (
            df_spine[["entity_id", "entity_key"]]
            .dropna()
            .drop_duplicates()
            .iterrows()
        ):
            eid, ekey = str(row["entity_id"]), str(row["entity_key"])
            if eid in schema_entity_ids:
                key_to_schema_ids.setdefault(ekey, []).append(eid)

    # ── 2. Build per-component-type schema dict (small) ────────────────────
    component_schemas: dict[str, dict] = {}
    for ctype in updated_components:
        schema: dict[str, dict] = {}
        for eid in key_to_schema_ids.get(ctype, []):
            for _, row in df_derived[df_derived["entity_id"] == eid].iterrows():
                fname = row.get("value")
                if _isnull(fname) or str(fname) in schema:
                    continue
                fname = str(fname)
                nullable = row.get("nullable")
                schema[fname] = {
                    "type": None if _isnull(row.get("type")) else str(row["type"]),
                    "nullable": True if _isnull(nullable) else bool(nullable),
                    "default": None if _isnull(row.get("default")) else row["default"],
                    "range": _parse_range(row.get("range")),
                }
        if schema:
            component_schemas[ctype] = schema

    # ── 3. Validate and coerce each component table via ibis + pandera ─────
    validated_comps: dict = {}
    violation_tables: list[ir.Table] = []

    for ctype, table in updated_components.items():
        t = table
        schema = component_schemas.get(ctype, {})

        if not schema:
            validated_comps[ctype] = t
            continue

        existing = set(t.columns)
        original_existing = set(existing)
        type_map = {
            fname: _IACS_TO_PYTHON_TYPE[fschema["type"]]
            for fname, fschema in schema.items()
            if fschema["type"] in _IACS_TO_PYTHON_TYPE
        }

        # Add missing typed columns as null
        for fname, py_type in type_map.items():
            if fname not in existing:
                t = t.mutate(**{fname: ibis.null().cast(_IBIS_DTYPE[py_type])})
                existing.add(fname)

        # Cast typed columns (bool: nullif "" only for original string columns)
        t_schema = t.schema()
        for fname, py_type in type_map.items():
            expr = t[fname]
            if py_type is bool and fname in original_existing and t_schema[fname].is_string():
                expr = expr.nullif("")
            t = t.mutate(**{fname: expr.cast(_IBIS_DTYPE[py_type])})

        # Apply defaults after casting so literal types match
        for fname, fschema in schema.items():
            default = fschema["default"]
            if default is None or fname not in existing:
                continue
            py_type = type_map.get(fname)
            if py_type is not None:
                lit = ibis.literal(_coerce_default(default, py_type)).cast(_IBIS_DTYPE[py_type])
            else:
                lit = ibis.literal(str(default))
            col = t[fname]
            if fschema["type"] == "str":
                col = col.nullif("")
            t = t.mutate(**{fname: col.fill_null(lit)})

        # Pandera type validation
        pa_columns = {
            fname: pa.Column(py_type, nullable=True)
            for fname, py_type in type_map.items()
            if fname in existing
        }
        if pa_columns:
            t = pa.DataFrameSchema(pa_columns).validate(t)

        validated_comps[ctype] = t

        # ── Collect violations as lazy ibis sub-queries ────────────────────
        for fname, fschema in schema.items():
            if fname not in existing:
                continue

            # Nullable violations
            if not fschema["nullable"]:
                violation_tables.append(
                    t.filter(t[fname].isnull()).select(
                        t["entity_id"],
                        t["component_index"],
                        ibis.literal(ctype).name("component_type"),
                        ibis.literal(fname).name("field"),
                        ibis.null().cast("string").name("value"),
                        ibis.literal("nullable").name("error_type"),
                    )
                )

            # Categorical range violations (str fields only)
            frange = fschema["range"]
            if fschema["type"] == "str" and isinstance(frange, list):
                violation_tables.append(
                    t.filter(t[fname].notnull() & ~t[fname].isin(frange)).select(
                        t["entity_id"],
                        t["component_index"],
                        ibis.literal(ctype).name("component_type"),
                        ibis.literal(fname).name("field"),
                        t[fname].cast("string").name("value"),
                        ibis.literal("range").name("error_type"),
                    )
                )

    # ── 4. Union all violation sub-queries ─────────────────────────────────
    _INVALID_COLS = ["entity_id", "component_index", "component_type", "field", "value", "error_type"]
    if violation_tables:
        invalid_table = violation_tables[0]
        for vt in violation_tables[1:]:
            invalid_table = invalid_table.union(vt)
    else:
        invalid_table = ibis.memtable(
            pd.DataFrame(columns=_INVALID_COLS).astype(
                {"entity_id": "str", "component_index": "int64", "component_type": "str", "field": "str", "value": "str", "error_type": "str"}
            )
        )

    return validated_comps, invalid_table

def validated_registry(validated_components: dict, invalid_field: ir.Table, registry: Registry) -> Registry:
    """Store the validated components back in the registry, including invalid_field.

    Parameters
    ----------
    validated_components : dict
        Dict of component_type -> coerced ibis Table (from ``validated_data``).
    invalid_field : ir.Table
        Table of constraint violations (from ``validated_data``), stored as the
        ``"invalid_field"`` component.
    registry : Registry
        The original registry, whose connection is reused.

    Returns
    -------
    Registry
        A new Registry with the validated components and ``invalid_field``.
    """
    conn = ibis.duckdb.connect()
    components = {}
    for comp_type, table in validated_components.items():
        conn.create_table(comp_type, table.to_pandas(), overwrite=True)
        components[comp_type] = conn.table(comp_type)
    conn.create_table("invalid_field", invalid_field.to_pandas(), overwrite=True)
    components["invalid_field"] = conn.table("invalid_field")
    return Registry(conn, components)
