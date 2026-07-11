import ast
import operator
from typing import Any

import pandas as pd
import pandera
import pandera.ibis as pa
from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.datatypes as dt
import ibis.expr.types as ir

from ...registry import Registry


_INFRA_TYPES = frozenset({"entity_id", "component_type", "invalid_field", "schema", "parent", "field"})

INPUT_COMPONENT_TYPES = ["entity_id"]

_ARITHMETIC_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_arithmetic_expr(expr: str) -> float | None:
    """Safely evaluate a simple numeric arithmetic expression string.

    Supports ``+ - * /`` and parentheses over int/float literals, e.g.
    ``"4 / 50"`` or ``"(1 + 2) * 3"``. Returns ``None`` if ``expr`` is not a
    valid expression of that form (e.g. it references names or calls).
    """
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC_OPS:
            return _ARITHMETIC_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ARITHMETIC_OPS:
            return _ARITHMETIC_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {node!r}")

    try:
        tree = ast.parse(expr, mode="eval").body
        return float(_eval(tree))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError):
        return None


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Extract components from the registry.

    Returns all registry components (not just INPUT_COMPONENT_TYPES) so that
    the downstream ``user_components`` node can filter the full set.
    """
    return registry._components


def user_components(components: dict) -> dict:
    """Filter infrastructure types, leaving only user-defined components for validation."""
    return {k: v for k, v in components.items() if k not in _INFRA_TYPES}



_IACS_TO_IBIS_TYPE: dict[str, dt.DataType] = {
    "str": dt.String(),
    "bool": dt.Boolean(),
    "int": dt.Int64(),
    "float": dt.Float64(),
    "rating": dt.Float64(),
}

_IACS_TO_PYTHON_TYPE: dict[str, type] = {
    "str": str,
    "bool": bool,
    "int": int,
    "float": float,
    "rating": float,
}

_IBIS_DTYPE = {bool: "boolean", str: "string", int: "int64", float: "float64"}

_INVALID_COLS = ["entity_id", "component_index", "component_type", "field", "value", "error_type"]
_INVALID_DTYPES = {
    "entity_id": "str", "component_index": "int64", "component_type": "str",
    "field": "str", "value": "str", "error_type": "str",
}


def _isnull(val) -> bool:
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


def _resolve_numeric_string(val):
    """Evaluate a numeric string that holds a simple arithmetic expression.

    Leaves plain numbers, null, and non-arithmetic strings untouched so they
    fall through to try_cast (which nulls invalid strings for later defaulting).
    """
    if not isinstance(val, str):
        return val
    s = val.strip()
    try:
        float(s)
        return val
    except ValueError:
        pass
    result = _eval_arithmetic_expr(s)
    return val if result is None else str(result)


def _coerce_default(val, py_type: type):
    if py_type is bool:
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes")
        return bool(val)
    try:
        return py_type(val)
    except (ValueError, TypeError):
        return val


@unpack_fields("validated_components", "invalid_field")
def validated_results(
    user_components: dict, field: ir.Table, entity_id: ir.Table,
) -> tuple[dict, ir.Table]:
    """Use the schemas defined by the ((field)) component to validate and coerce
    the data in each component.

    Materialise only the schema-defining rows (O(fields) records per component
    type), build ibis mutate chains for column addition, type casting, and
    default filling, then validate types, nullable constraints, and categorical
    ranges with :mod:`pandera.ibis` in a single lazy pass.  Constraint
    violations are collected from the raised :class:`pandera.errors.SchemaErrors`
    and unioned into ``invalid_field`` without pulling component data into memory.

    This is a simplified version of ``validated_data`` in ``validate_registry``
    that uses the raw ``field`` table rather than the inheritance-resolved
    ``derived_field``.

    Parameters
    ----------
    components : dict
        Dict of component_type -> ibis Table.
    field : ir.Table
        The ``field`` component table from the registry.
    entity_id : ir.Table
        One row per entity (value, path, alias, entity_key, filepath),
        used to map entity_key -> entity_id for schema lookup.

    Returns
    -------
    tuple[dict, ir.Table]
        ``(validated_components, invalid_field)`` where ``validated_components``
        is a dict of component_type -> coerced ibis Table, and ``invalid_field``
        is an ibis Table of rows that failed nullable or range constraints.
    """
    df_field = field.execute()
    df_entity = entity_id.execute()

    # Map entity_key -> entity_id for entities that have field definitions
    field_entity_ids = set(df_field["entity_id"].dropna().astype(str))
    key_to_eids: dict[str, list[str]] = {}
    for _, row in df_entity[["value", "entity_key"]].dropna().drop_duplicates().iterrows():
        eid, ekey = str(row["value"]), str(row["entity_key"])
        if eid in field_entity_ids:
            key_to_eids.setdefault(ekey, []).append(eid)

    # Build per-component-type schema from field rows
    component_schemas: dict[str, dict] = {}
    for ctype in user_components:
        schema: dict[str, dict] = {}
        for eid in key_to_eids.get(ctype, []):
            for _, row in df_field[df_field["entity_id"] == eid].iterrows():
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

    validated_comps: dict = {}
    violation_tables: list[ir.Table] = []

    for ctype, table in user_components.items():
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

        # Resolve simple arithmetic expressions (e.g. "4 / 50") in numeric string
        # columns before casting, so they evaluate instead of failing to null.
        t_schema = t.schema()
        arithmetic_cols = [
            fname for fname, py_type in type_map.items()
            if py_type in (float, int)
            and fname in original_existing
            and t_schema[fname].is_string()
        ]
        if arithmetic_cols:
            df = t.to_pandas()
            for fname in arithmetic_cols:
                df[fname] = df[fname].map(_resolve_numeric_string)
            t = ibis.memtable(df)

        # Cast typed columns; try_cast for numeric/bool strings so empty strings become NULL.
        # Pandera ibis does not support coerce for cross-type casting so we do this manually.
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

        # Build a pandera schema with nullable and isin constraints, then validate lazily.
        # A single validate(lazy=True) call collects all constraint violations at once
        # rather than raising on the first failure.
        pa_columns = {}
        for fname, fschema in schema.items():
            if fname not in existing:
                continue
            ibis_type = _IACS_TO_IBIS_TYPE.get(fschema["type"])
            checks = []
            frange = fschema["range"]
            if fschema["type"] == "str" and isinstance(frange, list):
                checks.append(pa.Check.isin(frange))
            pa_columns[fname] = pa.Column(
                ibis_type,
                nullable=fschema["nullable"],
                checks=checks or None,
            )

        if pa_columns:
            pa_schema = pa.DataFrameSchema(pa_columns)
            try:
                t = pa_schema.validate(t, lazy=True)
            except pandera.errors.SchemaErrors as exc:
                for err in exc.schema_errors:
                    col_name = getattr(err.schema, "name", None)
                    if col_name not in existing:
                        continue
                    reason = err.reason_code
                    if reason == pandera.errors.SchemaErrorReason.SERIES_CONTAINS_NULLS:
                        # check_output is a boolean column aligned with t: True means null
                        violation_tables.append(
                            t.filter(err.check_output).select(
                                t["entity_id"],
                                t["component_index"],
                                ibis.literal(ctype).name("component_type"),
                                ibis.literal(col_name).name("field"),
                                ibis.null().cast("string").name("value"),
                                ibis.literal("nullable").name("error_type"),
                            )
                        )
                    elif reason == pandera.errors.SchemaErrorReason.DATAFRAME_CHECK:
                        # isin violation: filter rows where value is not in the allowed set
                        frange = schema[col_name]["range"]
                        violation_tables.append(
                            t.filter(t[col_name].notnull() & ~t[col_name].isin(frange)).select(
                                t["entity_id"],
                                t["component_index"],
                                ibis.literal(ctype).name("component_type"),
                                ibis.literal(col_name).name("field"),
                                t[col_name].cast("string").name("value"),
                                ibis.literal("range").name("error_type"),
                            )
                        )

        validated_comps[ctype] = t

    if violation_tables:
        invalid_table = violation_tables[0]
        for vt in violation_tables[1:]:
            invalid_table = invalid_table.union(vt)
    else:
        invalid_table = ibis.memtable(
            pd.DataFrame(columns=_INVALID_COLS).astype(_INVALID_DTYPES)
        )

    return validated_comps, invalid_table


def time_filled_components(
    validated_components: dict,
    field: ir.Table,
    entity_id: ir.Table,
    load_time: Any = None,
) -> dict:
    """Backfill null time_dimension fields in validated_components with load_time.

    Used when loading a manifest that represents a snapshot as of a known
    point in time: the field flagged ``time_dimension: true`` in a component
    type's schema is set to ``load_time`` wherever it is still null. Values
    that are already set are left untouched. A no-op when ``load_time`` is
    not given.

    Parameters
    ----------
    validated_components : dict
        Dict of component_type -> validated ibis Table.
    field : ir.Table
        The ``field`` component table used to look up each component type's
        time_dimension field, if any.
    entity_id : ir.Table
        One row per entity, used to map entity_key -> entity_id for schema
        lookup (see ``validated_results``).
    load_time : Any, optional
        The point in time this load represents, e.g. a timestamp or date
        string.

    Returns
    -------
    dict
        ``validated_components``, with time_dimension fields backfilled.

    Raises
    ------
    ValueError
        If a component type has more than one time_dimension field.
    """
    if load_time is None:
        return validated_components

    df_field = field.execute()
    if "time_dimension" not in df_field.columns:
        return validated_components

    df_entity = entity_id.execute()
    key_by_eid = df_entity.set_index("value")["entity_key"]

    time_fields: dict[str, str] = {}
    for _, row in df_field.iterrows():
        if _isnull(row.get("time_dimension")) or not _coerce_default(row["time_dimension"], bool):
            continue
        fname = row.get("value")
        if _isnull(fname):
            continue
        ctype = key_by_eid.get(row["entity_id"])
        if ctype is None:
            continue
        fname = str(fname)
        existing = time_fields.get(ctype)
        if existing is not None and existing != fname:
            raise ValueError(
                f"Component type {ctype!r} has multiple time_dimension "
                f"fields {sorted({existing, fname})}; only one is allowed."
            )
        time_fields[ctype] = fname

    updated = dict(validated_components)
    for ctype, fname in time_fields.items():
        table = validated_components.get(ctype)
        if table is None or fname not in table.columns:
            continue
        df = table.execute()
        if df[fname].isna().any():
            df[fname] = df[fname].fillna(load_time)
            updated[ctype] = ibis.memtable(df)

    return updated


def validated_registry(
    registry: Registry,
    time_filled_components: dict,
    invalid_field: ir.Table,
) -> Registry:
    """Store validated components and constraint violations back into the registry."""
    registry.update({**time_filled_components, "invalid_field": invalid_field})
    return registry


FINAL_VAR = "validated_registry"
