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
_SKIP_COMP_TYPES = {"entity_id", "component_type", "invalid_field", "parent"}


def _explicit_parent_entries(
    components: dict,
    entity_id_table: ir.Table,
    user_entity_ids: set,
) -> dict[str, list[tuple[int, object]]]:
    """Reconstruct explicit ``parent`` component entries for export.

    ``updated_parent`` merges explicit and hierarchy-implied parent rows into a
    single table with only ``entity_id`` and ``parent_id`` columns, losing the
    original ``component_index`` and string reference (e.g. ``"task"``).

    This function recovers explicit parent entries by:
    1. Finding user entities that have ``component_type='parent'`` rows in the
       ``component_type`` table (which records only YAML-authored components).
    2. Computing the hierarchy-implied ``parent_id`` for each entity (the entity
       whose path is one level up in the dot-separated path hierarchy).
    3. Treating any ``parent_id`` that is NOT the hierarchy-implied one as explicit.
    4. Looking up the entity_key for each explicit ``parent_id`` to reconstruct
       the human-readable string reference used in YAML.

    Returns a mapping ``{entity_id: [(component_index, entry), ...]}``.
    """
    if "parent" not in components or "component_type" not in components:
        return {}

    parent_df = components["parent"].execute()
    ct_df = components["component_type"].execute()
    eid_df = entity_id_table.to_pandas()

    eid_to_path = eid_df.set_index("value")["path"].to_dict()
    eid_to_key = eid_df.set_index("value")["entity_key"].to_dict()
    path_to_eid = eid_df.set_index("path")["value"].to_dict()

    def _hierarchy_parent_id(eid: str) -> str | None:
        path = eid_to_path.get(eid, "")
        sep = path.find(":")
        if sep == -1:
            return None
        file_part, name_part = path[:sep], path[sep + 1:]
        if "." not in name_part:
            return None
        parent_name = name_part.rsplit(".", 1)[0]
        return path_to_eid.get(f"{file_part}:{parent_name}")

    # Entities with explicit parent components
    ct_parent = ct_df[ct_df["component_type"] == "parent"]
    if ct_parent.empty:
        return {}

    # All parent rows indexed by entity_id
    parent_by_eid: dict[str, list[str]] = {}
    for _, row in parent_df.iterrows():
        parent_by_eid.setdefault(str(row["entity_id"]), []).append(str(row["parent_id"]))

    result: dict[str, list[tuple[int, object]]] = {}
    for eid, group in ct_parent.groupby("entity_id"):
        if eid not in user_entity_ids:
            continue
        hierarchy_pid = _hierarchy_parent_id(eid)
        all_pids = parent_by_eid.get(eid, [])
        explicit_pids = sorted(
            [p for p in all_pids if p != hierarchy_pid],
            key=lambda p: eid_to_key.get(p, p),
        )
        if not explicit_pids:
            continue
        cidxs = sorted(group["component_index"].astype(int).tolist())
        for cidx, pid in zip(cidxs, explicit_pids):
            parent_key = eid_to_key.get(pid, pid)
            entry = {"parent": {"value": parent_key}}
            result.setdefault(eid, []).append((cidx, entry))

    return result


def _authored_component_keys(components: dict) -> set[tuple]:
    """Return (entity_id, component_index, component_type) for all user-authored rows.

    Uses the ``component_type`` table, which is populated exclusively from YAML
    loading, as the authoritative record.  Rows absent from this table (e.g.
    inherited ``field`` definitions from ``derived_field`` or hierarchy-implied
    ``parent`` rows from ``updated_parent``) are derived and must not be exported.

    Returns an empty set when the table is unavailable, which disables the filter.
    """
    if "component_type" not in components:
        return set()
    ct_df = components["component_type"].execute()
    return {
        (row["entity_id"], int(row["component_index"]), row["component_type"])
        for _, row in ct_df.iterrows()
    }


def _derived_comp_types(components: dict, entity_id_table: ir.Table) -> set[str]:
    """Return component type names marked as derived in the registry schema table.

    Looks up the ``schema`` component table for rows where ``derived`` is True,
    then maps those entity_ids back to entity_keys (which equal the component type name).
    """
    if "schema" not in components:
        return set()
    schema_df = components["schema"].execute()
    if "derived" not in schema_df.columns or schema_df.empty:
        return set()
    derived_rows = schema_df[schema_df["derived"] == True]
    if derived_rows.empty:
        return set()
    eid_df = entity_id_table.to_pandas()
    id_to_key = eid_df.set_index("value")["entity_key"].to_dict()
    return {id_to_key[eid] for eid in derived_rows["entity_id"] if eid in id_to_key}


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

    derived_types = _derived_comp_types(components, entity_id)
    authored_keys = _authored_component_keys(components)

    # {filepath: {entity_key: [(component_index, entry)]}}
    result: dict[str, dict[str, list]] = {}

    for comp_type, table in components.items():
        if comp_type in _SKIP_COMP_TYPES or comp_type in derived_types:
            continue

        df = table.execute()
        if "entity_id" not in df.columns or "component_index" not in df.columns:
            continue

        for _, row in df.iterrows():
            eid = row["entity_id"]
            cidx = int(row["component_index"])
            if eid not in user_entity_ids:
                continue
            if authored_keys and (eid, cidx, comp_type) not in authored_keys:
                continue

            entity_key = id_to_key.get(eid, eid)
            filepath = id_to_filepath.get(eid, "manifest.yaml")
            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type

            fields = {
                k: v for k, v in row.items()
                if k not in _METADATA_COLS
                and not k.endswith("_eid")
                and pd.notna(v)
            }

            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            else:
                entry = {key: fields}

            result.setdefault(filepath, {}).setdefault(entity_key, []).append(
                (cidx, entry)
            )

    for eid, parent_entries in _explicit_parent_entries(
        components, entity_id, user_entity_ids
    ).items():
        entity_key = id_to_key.get(eid, eid)
        filepath = id_to_filepath.get(eid, "manifest.yaml")
        result.setdefault(filepath, {}).setdefault(entity_key, []).extend(parent_entries)

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

    derived_types = _derived_comp_types(components, entity_id)
    authored_keys = _authored_component_keys(components)

    for comp_type, table in components.items():
        if comp_type in _SKIP_COMP_TYPES or comp_type in derived_types:
            continue

        df = table.execute()
        if "entity_id" not in df.columns or "component_index" not in df.columns:
            continue

        for _, row in df.iterrows():
            eid = row["entity_id"]
            cidx = int(row["component_index"])
            if eid not in user_entity_ids:
                continue
            if authored_keys and (eid, cidx, comp_type) not in authored_keys:
                continue

            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type

            fields = {
                k: v for k, v in row.items()
                if k not in _METADATA_COLS
                and not k.endswith("_eid")
                and pd.notna(v)
            }

            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            else:
                entry = {key: fields}

            entity_components.setdefault(eid, []).append(
                (cidx, entry)
            )

    for eid, parent_entries in _explicit_parent_entries(
        components, entity_id, user_entity_ids
    ).items():
        entity_components.setdefault(eid, []).extend(parent_entries)

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


def exported_manifest_filepaths(hierarchical_entity_first_data: dict, output_dir: str) -> list[str]:
    """Save hierarchical_entity_first_data to one YAML file per original source filepath.

    Parameters
    ----------
    hierarchical_entity_first_data : dict
        Mapping of original filepath → entity dict, as returned by
        ``hierarchical_entity_first_data``.
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
    for source_filepath, entities in hierarchical_entity_first_data.items():
        dest = out / Path(source_filepath).with_suffix(".yaml").name
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(entities, f, default_flow_style=False, allow_unicode=True)
        saved.append(str(dest))
    return sorted(saved)
