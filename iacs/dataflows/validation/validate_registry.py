import ast
import re

import pandas as pd
import pandera.ibis as pa
from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from ...registry import Registry
from ...utils import dhash


@extract_fields(dict(entity_id=ir.Table, field=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in a registry."""

    return registry._components

@unpack_fields("validated_components", "invalid_field")
def validated_data(
    components: dict, field: ir.Table | None, entity_id: ir.Table
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
    df_derived = field.execute()
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
    for ctype in components:
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

    for ctype, table in components.items():
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

        # Cast typed columns; use try_cast for numeric/bool string columns so
        # that empty strings (stored for missing fields) become NULL silently.
        t_schema = t.schema()
        for fname, py_type in type_map.items():
            expr = t[fname]
            if py_type in (bool, float, int) and fname in original_existing and t_schema[fname].is_string():
                t = t.mutate(**{fname: expr.try_cast(_IBIS_DTYPE[py_type])})
            else:
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

    return validated_comps, invalid_field


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
    registry.update({**validated_components, "invalid_field": invalid_field})
    return registry
