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

import re
from pathlib import Path

import pandas as pd
import yaml

from ..registry import Registry

_BUILTIN_FILEPATH = "builtins.components"
_SPINE_PATH_PAT = re.compile(r"^(.+)\[\d+\]\.[^[]+$")


def components(registry: Registry) -> dict:
    """Extract all component tables from the registry, including the spine.

    Parameters
    ----------
    registry : Registry
        The registry containing component tables.

    Returns
    -------
    dict
        A dict mapping component type names (including "spine") to ibis Tables.
    """
    return registry._components


_METADATA_COLS = {"entity_id", "component_index", "modifier"}


def entity_first_data(components: dict) -> dict:
    """Reconstruct the entity-centered nested dict from component tables.

    For each component type, groups rows by entity_id and serializes each row
    as a component entry. Tags (empty value, no other fields) become bare
    strings; scalar components become ``{type: value}``; multi-field components
    become ``{type: {field: value, ...}}``. Modifiers (e.g. "of") are appended
    to the component type key (e.g. "solution of").

    Parameters
    ----------
    components : dict
        Dict mapping component type names to ibis Tables, as returned by
        ``components``. Must include a ``"spine"`` key.

    Returns
    -------
    dict
        A dict of the form ``{entity_id: [component, ...]}`` where each
        component is a string (tag) or a single-key dict.
    """
    result: dict[str, list] = {}

    for comp_type, table in components.items():
        if comp_type == "spine":
            continue

        df = table.execute()

        for _, row in df.iterrows():
            entity_id = row["entity_id"]
            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type

            fields = {
                k: v for k, v in row.items()
                if k not in _METADATA_COLS and pd.notna(v)
            }

            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            elif len(fields) == 1 and "value" in fields:
                entry = {key: fields["value"]}
            else:
                entry = {key: fields}

            result.setdefault(entity_id, []).append(
                (int(row["component_index"]), entry)
            )

    return {
        eid: [e for _, e in sorted(entries)]
        for eid, entries in result.items()
    }


def manifest(entity_first_data: dict, output_path: str) -> None:
    """Write entity-first data to the filesystem as a YAML file.

    Parameters
    ----------
    entity_first_data : dict
        The entity-centered structure to serialize, as returned by
        ``entity_first_data``.
    output_path : str
        Path to write the YAML file to.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(entity_first_data, f, default_flow_style=False, allow_unicode=True)


def _coerce_value(s: str):
    """Parse a string back to its native Python type using YAML safe_load."""
    if not isinstance(s, str):
        return s
    try:
        return yaml.safe_load(s)
    except Exception:
        return s


def _entity_path_from_spine_path(spine_path: str, filepath: str) -> str | None:
    """Extract the manifest-relative entity path from a spine path string."""
    m = _SPINE_PATH_PAT.match(spine_path)
    if not m:
        return None
    prefix = m.group(1)
    if prefix.endswith(".data"):
        prefix = prefix[:-5]
    if filepath and prefix.startswith(filepath + ":"):
        return prefix[len(filepath) + 1:]
    colon_idx = prefix.find(":")
    if colon_idx != -1:
        return prefix[colon_idx + 1:]
    return prefix


# ---------------------------------------------------------------------------
# Hamilton DAG nodes for manifest_data reconstruction
# ---------------------------------------------------------------------------


def user_spine(registry: Registry) -> pd.DataFrame:
    """Filter the registry spine to only rows belonging to user (non-builtin) entities.

    Executes the spine ibis Table from the registry and removes all rows whose
    ``filepath`` column equals ``_BUILTIN_FILEPATH`` or is null. The result is
    a plain pandas DataFrame ready for downstream nodes.

    Parameters
    ----------
    registry : Registry
        The validated registry whose ``_components["spine"]`` ibis Table is the
        source of truth for all entity metadata.

    Returns
    -------
    pd.DataFrame
        Spine rows restricted to user-defined entities, with columns including
        at minimum ``entity_id``, ``component_index``, ``entity_key``,
        ``component_type``, ``modifier``, ``filepath``, and ``path``.
    """
    df = registry._components["spine"].execute()
    return df[df["filepath"].notna() & (df["filepath"] != _BUILTIN_FILEPATH)].reset_index(drop=True)


def entity_path_map(user_spine: pd.DataFrame) -> dict[str, str]:
    """Build a mapping from each user entity_id to its manifest-relative dot-path.

    Iterates over the user spine, deriving the manifest path for each entity
    from the spine ``path`` column via ``_entity_path_from_spine_path``. Only
    the first occurrence of each ``entity_id`` is used (all rows for the same
    entity share the same path). The result is a dict such as::

        {"eid-abc": "make_cats_happy.feed_and_water_cats.feed_cats", ...}

    The dot-separated path mirrors the hierarchical key structure of the
    original manifest YAML.

    Parameters
    ----------
    user_spine : pd.DataFrame
        Non-builtin spine rows, as returned by ``user_spine``.

    Returns
    -------
    dict[str, str]
        Mapping of ``entity_id`` strings to manifest-relative path strings.
    """
    result = {}
    for _, row in user_spine.iterrows():
        eid = row["entity_id"]
        if eid not in result:
            filepath = row.get("filepath") or ""
            path = _entity_path_from_spine_path(row["path"], filepath)
            if path:
                result[eid] = path
    return result


def user_component_tables(
    registry: Registry,
    user_spine: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Extract and execute only the component tables relevant to user entities.

    Iterates over all tables in ``registry._components``, skipping:

    - The ``"spine"`` table itself.
    - Any table that lacks a ``component_index`` column (e.g. ``updated_parent``).

    Executes each qualifying ibis Table to a pandas DataFrame and filters rows
    to those whose ``entity_id`` appears in the user entity set derived from
    ``user_spine``. Returns only tables that have at least one matching row.

    Parameters
    ----------
    registry : Registry
        The validated registry containing all component ibis Tables.
    user_spine : pd.DataFrame
        Non-builtin spine rows, used to determine the set of user entity IDs.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of component type name to the filtered, executed pandas
        DataFrame for that component type.
    """
    user_eids = set(user_spine["entity_id"])
    result = {}
    for comp_type, table in registry._components.items():
        if comp_type == "spine":
            continue
        df = table.execute()
        if "component_index" not in df.columns:
            continue
        filtered = df[df["entity_id"].isin(user_eids)]
        if not filtered.empty:
            result[comp_type] = filtered.reset_index(drop=True)
    return result


def entity_component_lists(
    user_component_tables: dict[str, pd.DataFrame],
    entity_path_map: dict[str, str],
) -> dict[str, list]:
    """Build each user entity's sorted, serialized component list.

    For every row in every component table, constructs a component entry in one
    of three forms:

    - **Tag** (bare string): when the row has no data fields beyond metadata, or
      the sole ``value`` field is an empty string.
    - **Scalar** ``{key: value}``: when the only non-metadata field is
      ``"value"`` and it is non-empty.
    - **Multi-field** ``{key: {field: value, ...}}``: when multiple non-metadata
      fields are present.

    The component type key is extended with the modifier when present
    (e.g. ``"solution of"``). All field values are coerced from strings to
    native Python types via ``_coerce_value``. Entries are accumulated as
    ``(component_index, entry)`` tuples and sorted ascending by index before
    the index is discarded.

    Parameters
    ----------
    user_component_tables : dict[str, pd.DataFrame]
        Filtered, executed component DataFrames keyed by component type name,
        as returned by ``user_component_tables``.
    entity_path_map : dict[str, str]
        Mapping of entity_id to manifest path, used to restrict processing to
        known user entities.

    Returns
    -------
    dict[str, list]
        Mapping of ``entity_id`` to an ordered list of component entries
        (strings or dicts), ready for embedding in the manifest structure.
    """
    result = {}
    for comp_type, df in user_component_tables.items():
        for _, row in df.iterrows():
            eid = row["entity_id"]
            if eid not in entity_path_map:
                continue
            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type
            fields = {
                k: _coerce_value(v) for k, v in row.items()
                if k not in _METADATA_COLS and pd.notna(v)
            }
            if not fields or (len(fields) == 1 and fields.get("value") == ""):
                entry = key
            else:
                entry = {key: fields}
            result.setdefault(eid, []).append((int(row["component_index"]), entry))
    return {
        eid: [e for _, e in sorted(entries, key=lambda x: x[0])]
        for eid, entries in result.items()
    }


def manifest_data(
    entity_component_lists: dict[str, list],
    entity_path_map: dict[str, str],
) -> dict:
    """Assemble the final nested manifest dict from entity component lists.

    Reconstructs the hierarchical entity-centered manifest structure by
    traversing the dot-separated manifest paths in shallow-first order
    (sorted by path depth). For each entity:

    - If the entity has child entities (i.e. some other path starts with
      ``manifest_path + "."``), its own component list is nested under a
      ``"data"`` key within the entity's dict node.
    - If the entity is a leaf (no children), its component list is stored
      directly as the value at its key.

    Empty component lists for parent entities are omitted (no ``"data"`` key
    is added when the list is empty).

    Parameters
    ----------
    entity_component_lists : dict[str, list]
        Ordered component entries per entity, as returned by
        ``entity_component_lists``.
    entity_path_map : dict[str, str]
        Mapping of entity_id to manifest-relative dot-path, as returned by
        ``entity_path_map``.

    Returns
    -------
    dict
        Nested dict mirroring the original manifest YAML structure, with
        component lists (or dicts with a ``"data"`` sub-key) at each entity
        leaf or parent node.
    """
    all_paths = set(entity_path_map.values())
    sorted_items = sorted(entity_path_map.items(), key=lambda x: x[1].count("."))
    root = {}
    for eid, path in sorted_items:
        components = entity_component_lists.get(eid, [])
        has_children = any(p.startswith(path + ".") for p in all_paths if p != path)
        parts = path.split(".")
        node = root
        for part in parts[:-1]:
            if isinstance(node.get(part), list):
                node[part] = {"data": node[part]}
            node = node.setdefault(part, {})
        key = parts[-1]
        if has_children:
            if components:
                node[key] = {"data": components}
            else:
                node[key] = {}
        else:
            node[key] = components
    return root
