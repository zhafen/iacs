"""Hamilton DAG for converting entity-centered data to component-centered data."""

import hashlib
import re
from pathlib import Path
from typing import Any

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import pandas as pd
import pydantic
import yaml

from ..registry import Registry
from ..utils import dhash


def raw_entity_first_data(input_dir: str) -> dict:
    """Load all yaml files from the input directory and its sub directories.

    Parameters
    ----------
    input_dir : str

    Returns
    -------
    dict
        A dictionary containing all the entities from across the files,
        with no transformations applied.
    """
    result = {}
    for path in Path(input_dir).rglob("*.y*ml"):
        if path.suffix in (".yaml", ".yml"):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            result.update(data)
    return result


def db_conn() -> ibis.BaseBackend:
    """Create an Ibis database connection for the data to be stored in.

    Returns
    -------
    ibis.BaseBackend
        An Ibis backend containing the component tables.
    """
    return ibis.duckdb.connect()


def _add_component_pairs(
    entity_path: str, index: int, component, result: list
) -> None:
    """Append (path, value) pairs for one component entry to result.

    Parameters
    ----------
    entity_path : str
        The dot-separated path to the owning entity, e.g. "a.b.c".
    index : int
        The 0-based position of this component in the entity's list
        (bare-string tags count toward the index).
    component : str | dict
        The raw YAML component value.
    result : list
        Accumulator of (path, value) string tuples.
    """
    prefix = f"{entity_path}[{index}]"
    if isinstance(component, str):
        # Tag component: bare string, no associated value.
        result.append((f"{prefix}.{component}", ""))
    elif isinstance(component, dict):
        key = next(iter(component))
        value = component[key]
        if isinstance(value, dict):
            # Component with sub-fields, e.g. {"requirement": {"priority": 1}}.
            for sub_key, sub_val in value.items():
                str_val = "" if sub_val is None else str(sub_val)
                result.append((f"{prefix}.{key}.{sub_key}", str_val))
        else:
            # Simple scalar component, e.g. {"description": "..."}.
            str_val = "" if value is None else str(value)
            result.append((f"{prefix}.{key}", str_val))


def _flatten_to_pathvalue(data: dict, parent_path: str = "") -> list[tuple[str, str]]:
    """Recursively flatten entity-first data into (path, value) string pairs.

    For flat entities (list value) the path is ``entity[N].key``.
    For nested entities (dict value with an optional ``data`` key) the entity's
    own components are at ``entity.data[N].key`` and sub-entities are processed
    recursively.
    """
    result = []
    for entity_key, entity_value in data.items():
        entity_path = f"{parent_path}.{entity_key}" if parent_path else entity_key
        if isinstance(entity_value, list):
            for i, component in enumerate(entity_value):
                _add_component_pairs(entity_path, i, component, result)
        elif isinstance(entity_value, dict):
            # Entity's own components live under the "data" key (if present).
            for i, component in enumerate(entity_value.get("data", [])):
                _add_component_pairs(f"{entity_path}.data", i, component, result)
            # Recurse into sub-entities (every key except "data").
            sub_entities = {k: v for k, v in entity_value.items() if k != "data"}
            result.extend(_flatten_to_pathvalue(sub_entities, entity_path))
    return result


def pathvalue_pairs(raw_entity_first_data: dict, db_conn: ibis.BaseBackend) -> ibis.Table:
    """Convert the raw entity-first data into a database table with two fields:
    path and value, both of type str. This is the first step in the transformation
    process, and serves as a way to inspect the raw data in a tabular format before
    applying the more complex transformations.

    Parameters
    ----------
    raw_entity_first_data : dict
    conn : ibis.BaseBackend

    Returns
    -------
    ibis.Table
        A table with columns "path" and "value", where "path" is the entity path
        (e.g. "a.b.c[0].key") and "value" is the corresponding leaf value from
        the raw data, serialized as a string.
    """
    pairs = _flatten_to_pathvalue(raw_entity_first_data)
    df = pd.DataFrame(pairs, columns=["path", "value"])
    db_conn.create_table("pathvalue_pairs", df, overwrite=True)
    return db_conn.table("pathvalue_pairs")


_PATH_RE = re.compile(r"^(.+)\[(\d+)\]\.(.+)$")


def _parse_one_path(path: str) -> dict | None:
    """Parse a path string into spine fields.

    Returns a dict with spine columns plus 'entity_path' (for hierarchy) and
    '_spine_path' (for deduplication), or None if the path does not match
    the expected ``entity_prefix[index].component_type`` format.
    """
    m = _PATH_RE.match(path)
    if not m:
        return None
    entity_prefix, idx_str, after = m.group(1), m.group(2), m.group(3)

    # First dot-segment of 'after' is the full component type (may contain spaces).
    component_type_full = after.split(".")[0]

    # Strip the '.data' suffix added for nested entities' own components.
    if entity_prefix.endswith(".data"):
        entity_path = entity_prefix[:-5]
    else:
        entity_path = entity_prefix

    # Split 'solution of' → type='solution', modifier='of'.
    parts = component_type_full.split(" ", 1)
    component_type = parts[0]
    modifier = parts[1] if len(parts) > 1 else None

    spine_path = f"{entity_prefix}[{idx_str}].{component_type_full}"

    return {
        "entity_id": dhash(entity_path),
        "component_index": int(idx_str),
        "entity_key": entity_path.split(".")[-1],
        "component_type": component_type,
        "modifier": modifier,
        "path": spine_path,
        "entity_path": entity_path,
        "_spine_path": spine_path,
    }


@unpack_fields("spine", "hierarchy")
def parsed_paths(pathvalue_pairs: ibis.Table) -> tuple[ibis.Table, ibis.Table]:
    """Hash the paths into entity IDs, and extract the parent-child relationships
    and component types.

    Parameters
    ----------
    pathvalue_pairs : ibis.Table

    Returns
    -------
    spine : ibis.Table
        The spine is the shared index of the registry that contains one row per
        component instance, with the entity_id, component type, and original path.
        The entity_id and component_index columns are the actual index of the registry, and the component_type column is used to pivot into component tables.
        It has the below columns:
        - entity_id: the hashed ID of the entity
        - component_index: Index of the component in the original list of components for that entity (derived from the path)
        - entity_key: The name of the entity, the last part of the path for an entity.
        - component_type: the type of the component
        - modifier: any modifiers for the component instance, which may affect interpretation of the fields (e.g. "parent" vs "parent of")
        - path: the original path

    hierarchy : ibis.Table
        The parent-child relationships between entities as encoded in the paths.
        Note that the ((parent)) component instances in the pathvalue_pairs
        may encode additional relationships.
        A table with the below columns:
        - entity_id: the hashed ID of the entity (derived from the path)
        - parent_id: the hashed ID of the parent entity (derived from the parent path)
    """
    SPINE_COLS = [
        "entity_id", "component_index", "entity_key",
        "component_type", "modifier", "path",
    ]

    df = pathvalue_pairs.to_pandas()

    spine_rows: list[dict] = []
    seen_spine: set[str] = set()
    entity_paths: list[str] = []
    seen_entity_paths: set[str] = set()

    for path in df["path"]:
        row = _parse_one_path(path)
        if row is None:
            continue
        sp = row["_spine_path"]
        if sp not in seen_spine:
            seen_spine.add(sp)
            spine_rows.append(row)
        ep = row["entity_path"]
        if ep not in seen_entity_paths:
            seen_entity_paths.add(ep)
            entity_paths.append(ep)

    spine_df = (
        pd.DataFrame(spine_rows)[SPINE_COLS]
        if spine_rows
        else pd.DataFrame(columns=SPINE_COLS)
    )

    hierarchy_rows = []
    for ep in entity_paths:
        if "." not in ep:
            continue
        parent_path = ep.rsplit(".", 1)[0]
        if parent_path in seen_entity_paths:
            hierarchy_rows.append({
                "entity_id": dhash(ep),
                "parent_id": dhash(parent_path),
            })

    hierarchy_df = pd.DataFrame(
        hierarchy_rows if hierarchy_rows else [],
        columns=["entity_id", "parent_id"],
    )

    return ibis.memtable(spine_df), ibis.memtable(hierarchy_df)


def incomplete_component_tables(
    db_conn: ibis.BaseBackend,
    pathvalue_pairs: ibis.Table,
    spine: ibis.Table,
) -> dict[str, ibis.Table]:
    """Join the pathvalue_pairs and spine on path and group the results by component
    type to create a dictionary of component tables. The result is "incomplete" because
    it doesn't incorporate information from the hierarchy yet.

    Parameters
    ----------
    conn : ibis.BaseBackend
        An Ibis backend containing the component tables.

    validated_components : dict[str, ibis.Table | dict]

    Returns
    -------
    Registry
        A registry object.
    """
    return

def component_tables(
    incomplete_component_tables: dict[str, ibis.Table],
    hierarchy: ibis.Table
) -> dict[str, ibis.Table]:
    """Incorporate the hierarchy information into the component tables by unioning it
    with the parent component table.

    Parameters
    ----------
    incomplete_component_tables : dict[str, ibis.Table]

    Returns
    -------
    dict[str, ibis.Table]
        A dictionary of component tables, ready to be loaded into the registry.
    """
    return

def registry(db_conn: ibis.BaseBackend, spine: ibis.Table, component_tables: dict[str, ibis.Table]) -> Registry:
    """Load the constituents of a registry into the registry object. The spine is used as the shared index for the registry, and the component tables are attached to it.

    Parameters
    ----------
    component_tables : dict[str, ibis.Table]

    Returns
    -------
    Registry
        A registry object containing the component tables.
    """
    return

