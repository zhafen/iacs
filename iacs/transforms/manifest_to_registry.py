"""Hamilton DAG for converting entity-centered data to component-centered data."""

import re
from pathlib import Path

import ibis
import pandas as pd
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


def pathvalue_pairs(raw_entity_first_data: dict) -> ibis.Table:
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
    return ibis.memtable(df)


_PATH_RE = re.compile(r"^(.+)\[(\d+)\]\.(.+)$")


def _parse_one_path(path: str) -> dict | None:
    """Parse a path string into spine fields.

    Returns a dict with spine columns plus 'entity_path' and
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


def spine(pathvalue_pairs: ibis.Table) -> ibis.Table:
    """Hash the paths into entity IDs, and extract the parent-child relationships
    and component types.

    Parameters
    ----------
    pathvalue_pairs : ibis.Table
    db_conn : ibis.BaseBackend

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
    # DuckDB requires non-NULL column types; modifier may be all-None.
    spine_df["modifier"] = spine_df["modifier"].astype(pd.StringDtype())

    return ibis.memtable(spine_df)


def component_tables(
    pathvalue_pairs: ibis.Table,
    spine: ibis.Table,
) -> dict[str, ibis.Table]:
    """Join the pathvalue_pairs and spine on path and group the results by component
    type to create a dictionary of component tables.

    Parameters
    ----------
    db_conn : ibis.BaseBackend
    pathvalue_pairs : ibis.Table
    spine : ibis.Table

    Returns
    -------
    dict[str, ibis.Table]
        Keys are component types; each value is an ibis Table with columns
        entity_id, component_index, modifier, and one column per sub-field
        (or "value" for scalar components).
    """
    pvp_df = pathvalue_pairs.to_pandas()
    spine_df = spine.to_pandas()

    def _spine_path_and_field(pvp_path):
        parsed = _parse_one_path(pvp_path)
        if parsed is None:
            return None, None
        sp = parsed["path"]
        field = pvp_path[len(sp) + 1:] if pvp_path != sp else "value"
        return sp, field

    pvp_df[["spine_path", "field_name"]] = pvp_df["path"].apply(
        lambda p: pd.Series(_spine_path_and_field(p))
    )

    spine_for_join = spine_df[
        ["entity_id", "component_index", "component_type", "modifier", "path"]
    ].rename(columns={"path": "_spine_path"})
    merged = pvp_df.merge(
        spine_for_join, left_on="spine_path", right_on="_spine_path", how="inner"
    )

    result = {}
    for comp_type, group in merged.groupby("component_type"):
        instances: dict[tuple, dict] = {}
        for _, row in group.iterrows():
            key = (row["entity_id"], row["component_index"])
            if key not in instances:
                instances[key] = {
                    "entity_id": row["entity_id"],
                    "component_index": row["component_index"],
                    "modifier": row["modifier"],
                }
            instances[key][row["field_name"]] = row["value"]

        comp_df = pd.DataFrame(list(instances.values()))
        comp_df["modifier"] = comp_df["modifier"].astype(pd.StringDtype())
        result[comp_type] = ibis.memtable(comp_df)

    return result


def registry(spine: ibis.Table, component_tables: dict[str, ibis.Table]) -> Registry:
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

