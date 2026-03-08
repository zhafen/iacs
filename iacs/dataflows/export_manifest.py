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

from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir
import pandas as pd
import yaml

from ..registry import Registry

_BUILTIN_FILEPATH = "builtins.components"
_SPINE_PATH_PAT = re.compile(r"^(.+)\[\d+\]\.[^[]+$")

@extract_fields({"spine": ir.Table})
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


def entity_first_data(components: dict, spine: ir.Table) -> dict:
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