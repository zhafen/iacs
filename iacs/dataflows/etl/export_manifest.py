"""Hamilton DAG for converting component-centered registry data back to entity-centered manifest data.

DAG structure (dependency order):

    registry
        └── user_spine
        │       └── entity_path_map
        └── user_component_tables (also depends on user_spine)
                └── entity_component_lists (also depends on entity_path_map)
                        └── manifest_data (also depends on entity_path_map)
                                └── entity_first_data (via components, separate branch)
                                └── manifest (terminal, also depends on output_path)

The manifest_data branch reconstructs a hierarchically nested entity-centered
dict from the flat component tables in the registry, excluding builtin entities
and handling parent/child nesting with the "data" key convention.

The components/entity_first_data/manifest branch is a separate, simpler path
that serializes the registry directly to YAML without path-based nesting.
"""

from pathlib import Path

import yaml
from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir
import pandas as pd

from ...registry import Registry

_BUILTIN_FILEPATH = "builtins.components"

@extract_fields({"entity_id": ir.Table})
def components(registry: Registry) -> dict:
    """Extract all component tables from the registry, including entity_id_table.

    Parameters
    ----------
    registry : Registry
        The registry containing component tables.

    Returns
    -------
    dict
        A dict mapping component type names (including "entity_id_table") to ibis Tables.
    """
    return registry._components


_METADATA_COLS = {"entity_id", "component_index", "modifier"}


def entity_first_data(components: dict, entity_id: ir.Table) -> dict:
    """Reconstruct the entity-centered nested dict from component tables.

    For each component type, groups rows by entity_id and serializes each row
    as a component entry. Tags (empty value, no other fields) become bare
    strings; all other components become ``{type: {field: value, ...}}``.
    Modifiers (e.g. "of") are appended to the component type key
    (e.g. "solution of"). Builtin entities are excluded.

    Parameters
    ----------
    components : dict
        Dict mapping component type names to ibis Tables, as returned by
        ``components``. Must include an ``"entity_id"`` key.

    Returns
    -------
    dict
        A dict of the form ``{entity_key: [component, ...]}`` where each
        component is a string (tag) or a single-key dict.
    """
    spine_df = entity_id.to_pandas()
    user_rows = spine_df[~spine_df["filepath"].str.startswith("builtins")]
    user_entity_ids = set(user_rows["value"].unique())
    id_to_key = (
        spine_df.drop_duplicates("value")
        .set_index("value")["entity_key"]
        .to_dict()
    )
    id_to_filepath = (
        spine_df.drop_duplicates("value")
        .set_index("value")["filepath"]
        .to_dict()
    )

    # {filepath: {entity_key: [(component_index, entry)]}}
    result: dict[str, dict[str, list]] = {}

    for comp_type, table in components.items():
        if comp_type in ("entity_id", "component_type", "invalid_field"):
            continue

        df = table.execute()
        if "entity_id" not in df.columns or "component_index" not in df.columns:
            continue

        for _, row in df.iterrows():
            eid = row["entity_id"]
            if eid not in user_entity_ids:
                continue

            entity_key = id_to_key.get(eid, eid)
            filepath = id_to_filepath.get(eid, "manifest.yaml")
            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type

            fields = {
                k: v for k, v in row.items()
                if k not in _METADATA_COLS and pd.notna(v)
            }

            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            else:
                entry = {key: fields}

            result.setdefault(filepath, {}).setdefault(entity_key, []).append(
                (int(row["component_index"]), entry)
            )

    return {
        fp: {
            ekey: [e for _, e in sorted(entries, key=lambda x: x[0])]
            for ekey, entries in entities.items()
        }
        for fp, entities in result.items()
    }


def _get_or_create_node(
    path_parts: list[str], hierarchical: dict, node_of: dict
) -> dict:
    """Return the dict node for a given entity path, creating structural nodes as needed.

    ``node_of[path]`` stores the entity's own dict value (after any list→dict conversion).
    If the entity's value is still a list (no children have been added yet), it is
    converted to ``{"data": list}`` on first access as a parent.
    """
    if not path_parts:
        return hierarchical

    path = ".".join(path_parts)
    key = path_parts[-1]

    if path in node_of:
        val = node_of[path]
        if isinstance(val, list):
            parent = _get_or_create_node(path_parts[:-1], hierarchical, node_of)
            parent[key] = {"data": val}
            node_of[path] = parent[key]
        return node_of[path]

    parent = _get_or_create_node(path_parts[:-1], hierarchical, node_of)
    if key not in parent:
        parent[key] = {}
    elif isinstance(parent[key], list):
        parent[key] = {"data": parent[key]}
    node_of[path] = parent[key]
    return node_of[path]


def hierarchical_entity_first_data(components: dict, entity_id: ir.Table) -> dict:
    """Reconstruct a hierarchically nested entity-centered dict from component tables.

    Like ``entity_first_data`` but nests child entities under their parents using
    the dot-separated entity path stored in the registry.  When a parent has both
    its own components and child entities, the parent's components are placed under
    a ``"data"`` key.

    Parameters
    ----------
    components : dict
        Dict mapping component type names to ibis Tables, as returned by
        ``components``.
    entity_id : ir.Table
        The entity spine table extracted from ``components``.

    Returns
    -------
    dict
        ``{filepath: {entity_key: ...}}`` where nested entities are dicts
        containing a ``"data"`` key (own components) and child-entity keys.
    """
    spine_df = entity_id.to_pandas()
    user_rows = spine_df[~spine_df["filepath"].str.startswith("builtins")]
    user_entity_ids = set(user_rows["value"].unique())

    id_to_filepath: dict[str, str] = {}
    id_to_path_in_file: dict[str, str] = {}

    for _, row in user_rows.iterrows():
        eid = str(row["value"])
        filepath = str(row["filepath"])
        full_path = str(row["path"])
        id_to_filepath[eid] = filepath
        id_to_path_in_file[eid] = full_path[len(filepath) + 1:]

    entity_components: dict[str, list] = {}

    for comp_type, table in components.items():
        if comp_type in ("entity_id", "component_type", "invalid_field"):
            continue

        df = table.execute()
        if "entity_id" not in df.columns or "component_index" not in df.columns:
            continue

        for _, row in df.iterrows():
            eid = row["entity_id"]
            if eid not in user_entity_ids:
                continue

            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type

            fields = {
                k: v for k, v in row.items()
                if k not in _METADATA_COLS and pd.notna(v)
            }

            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            else:
                entry = {key: fields}

            entity_components.setdefault(eid, []).append(
                (int(row["component_index"]), entry)
            )

    sorted_entity_components = {
        eid: [e for _, e in sorted(entries, key=lambda x: x[0])]
        for eid, entries in entity_components.items()
    }

    filepath_entities: dict[str, list[tuple[str, str]]] = {}
    for eid in user_entity_ids:
        if eid in id_to_filepath:
            filepath_entities.setdefault(id_to_filepath[eid], []).append(
                (eid, id_to_path_in_file[eid])
            )

    result: dict[str, dict] = {}
    for filepath, entity_list in filepath_entities.items():
        entity_list.sort(key=lambda x: (len(x[1].split(".")), x[1]))

        hierarchical: dict = {}
        node_of: dict[str, object] = {}

        for eid, path_in_file in entity_list:
            parts = path_in_file.split(".")
            entity_key = parts[-1]
            comps = sorted_entity_components.get(eid, [])

            if len(parts) == 1:
                hierarchical[entity_key] = comps
                node_of[path_in_file] = hierarchical[entity_key]
            else:
                parent_node = _get_or_create_node(parts[:-1], hierarchical, node_of)
                parent_node[entity_key] = comps
                node_of[path_in_file] = parent_node[entity_key]

        result[filepath] = hierarchical

    return result


def exported_manifest_filepaths(entity_first_data: dict, output_dir: str) -> list[str]:
    """Save entity_first_data to one YAML file per original source filepath.

    Parameters
    ----------
    entity_first_data : dict
        Mapping of original filepath → entity dict, as returned by
        ``entity_first_data``.
    output_dir : str
        Directory to write the manifest YAML files into.

    Returns
    -------
    list[str]
        The saved filepaths, sorted for determinism.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for source_filepath, entities in entity_first_data.items():
        dest = out / Path(source_filepath).with_suffix(".yaml").name
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(entities, f, default_flow_style=False, allow_unicode=True)
        saved.append(str(dest))
    return sorted(saved)
