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
    select_cols = [c for c in ("value", "type") if c in field.columns]
    if len(select_cols) < 2:
        return field

    schema_df = (
        field
        .filter(field["entity_id"] == field_entity_id)
        .select(select_cols)
        .execute()
    )

    type_map: dict[str, type] = {}
    for _, row in schema_df.iterrows():
        name, dtype = row["value"], row["type"]
        if pd.notna(name) and name and pd.notna(dtype) and dtype in _IACS_TO_PYTHON_TYPE:
            type_map[str(name)] = _IACS_TO_PYTHON_TYPE[str(dtype)]

    if not type_map:
        return field

    # ── Lazily cast typed columns using ibis expressions ──────────────────
    # pandera ibis validates ibis column types (not raw values), so the casts
    # must be applied to the ibis expression tree before pandera sees it.
    # For bool columns we also convert "" → NULL first; DuckDB raises on
    # CAST('' AS BOOLEAN) but handles NULL cleanly.
    existing = set(field.columns)
    _IBIS_DTYPE = {bool: "boolean", str: "string", int: "int64", float: "float64"}

    result = field
    for col_name, col_type in type_map.items():
        if col_name not in existing:
            continue
        expr = result[col_name]
        if col_type is bool:
            expr = expr.nullif("")
        result = result.mutate(**{col_name: expr.cast(_IBIS_DTYPE[col_type])})

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

    Parameters
    ----------
    validated_field : ir.Table
        _description_
    updated_parent : ir.Table
        _description_

    Returns
    -------
    ir.Table
        _description_
    """

    return


def updated_components(
    updated_parent: ir.Table, derived_field: ir.Table, registry: Registry
) -> dict:
    """Store the components updated so far back in the registry.

    Parameters
    ----------
    updated_parent : ir.Table
        _description_
    derived_field : ir.Table
        _description_

    Returns
    -------
    Registry
        _description_
    """

    return

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
