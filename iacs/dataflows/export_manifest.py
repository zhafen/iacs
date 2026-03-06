"""Hamilton DAG for converting component-centered registry data back to entity-centered manifest data."""

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


def manifest_data(registry: Registry) -> dict:
    """Reconstruct the entity-centered manifest dict from a Registry.

    Converts the component-centered Registry back to the hierarchical
    entity-centered format matching the original manifest YAML structure.
    Builtin components are excluded.

    Parameters
    ----------
    registry : Registry

    Returns
    -------
    dict
        Nested dict matching the structure of the original manifest YAML.
    """
    comps = registry._components
    spine_df = comps["spine"].execute()

    # Filter out builtins.
    user_spine = spine_df[
        spine_df["filepath"].notna() & (spine_df["filepath"] != _BUILTIN_FILEPATH)
    ].copy()

    # Build entity_id -> manifest_path mapping (one entry per unique entity).
    entity_path_map: dict[str, str] = {}
    for _, row in user_spine.iterrows():
        eid = row["entity_id"]
        if eid in entity_path_map:
            continue
        filepath = row.get("filepath")
        manifest_path = _entity_path_from_spine_path(str(row["path"]), str(filepath) if pd.notna(filepath) else "")
        if manifest_path:
            entity_path_map[eid] = manifest_path

    user_eids = set(entity_path_map)

    # Build entity_id -> sorted component list.
    entity_components: dict[str, list] = {eid: [] for eid in user_eids}
    for comp_type, table in comps.items():
        if comp_type == "spine":
            continue
        df = table.execute()
        if "component_index" not in df.columns:
            continue
        for _, row in df.iterrows():
            eid = row["entity_id"]
            if eid not in entity_components:
                continue
            modifier = row.get("modifier")
            key = f"{comp_type} {modifier}" if pd.notna(modifier) and modifier else comp_type
            raw_fields = {k: v for k, v in row.items() if k not in _METADATA_COLS and pd.notna(v)}
            if not raw_fields or (len(raw_fields) == 1 and raw_fields.get("value") == ""):
                entry = key
            elif len(raw_fields) == 1 and "value" in raw_fields:
                entry = {key: _coerce_value(raw_fields["value"])}
            else:
                entry = {key: {k: _coerce_value(v) for k, v in raw_fields.items()}}
            entity_components[eid].append((int(row["component_index"]), entry))

    for eid in entity_components:
        entity_components[eid] = [e for _, e in sorted(entity_components[eid], key=lambda x: x[0])]

    # Determine which manifest paths have children.
    all_manifest_paths = set(entity_path_map.values())

    def _has_children(manifest_path: str) -> bool:
        prefix = manifest_path + "."
        return any(p.startswith(prefix) for p in all_manifest_paths if p != manifest_path)

    # Build nested manifest dict, parents before children.
    result: dict = {}
    for eid, manifest_path in sorted(entity_path_map.items(), key=lambda x: x[1].count(".")):
        comp_list = entity_components[eid]
        parts = manifest_path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        leaf = parts[-1]
        if _has_children(manifest_path):
            if leaf not in target:
                target[leaf] = {}
            if comp_list:
                target[leaf]["data"] = comp_list
        else:
            target[leaf] = comp_list

    return result
