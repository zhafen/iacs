"""This module validates the data in the registry against their schema and coerces or
warns as appropriate.
"""

import re

import pandas as pd
import pandera.ibis as pa
from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ..registry import Registry
from ..utils import dhash


_ENTITY_PATH_PATTERN = re.compile(r"^(.+?)\[\d+\]\..+$")


@extract_fields(dict(spine=ir.Table, parent=ir.Table, field=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in a registry."""

    return registry._components


def updated_parent(spine: ir.Table, parent: ir.Table) -> ir.Table:
    """Convert the paths in the spine into parent-child relationships and
    add them to the parent component.

    Produces two kinds of parent-child rows:

    1. **Hierarchy-implied**: every nested entity (whose entity path contains
       a dot after the file-id separator) is a child of the entity at the
       path one level up.
    2. **Explicit**: rows in the ``parent`` component table declare a parent
       via a string reference (``value``), which is resolved to an
       ``entity_id`` by matching against ``entity_key`` in the spine.

    Parameters
    ----------
    spine : ir.Table
        The spine table produced by ``load_manifest.spine``, containing at
        minimum the columns ``entity_id``, ``entity_key``, and ``path``.
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
    df_spine = spine.to_pandas()

    # ── Part 1: hierarchy-implied parents from entity path nesting ────────
    def extract_entity_path(path):
        m = _ENTITY_PATH_PATTERN.match(path)
        if not m:
            return None
        prefix = m.group(1)
        return prefix[:-5] if prefix.endswith(".data") else prefix

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

    df_spine["entity_path"] = df_spine["path"].apply(extract_entity_path)
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
            lit = ibis.literal(default_val).cast(_IBIS_DTYPE[col_type])
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

def validated_components(updated_components: dict, derived_field: ir.Table) -> dict:
    """Use the schemas defined by the ((field)) component to validate and coerce the data in each component.

    Parameters
    ----------
    updated_components : dict
        _description_
    derived_field : _type_
        _description_

    Returns
    -------
    dict
        _description_
    """

    return

def validated_registry(validated_components: dict, registry: Registry) -> Registry:
    """Store the components back in the registry.

    Parameters
    ----------
    validated_components : dict
        _description_
    registry : Registry
        _description_

    Returns
    -------
    Registry
        _description_
    """

    return
