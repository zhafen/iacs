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

from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir
import pandas as pd

from ..registry import Registry

_BUILTIN_FILEPATH = "builtins.components"

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
    strings; all other components become ``{type: {field: value, ...}}``.
    Modifiers (e.g. "of") are appended to the component type key
    (e.g. "solution of"). Builtin entities are excluded.

    Parameters
    ----------
    components : dict
        Dict mapping component type names to ibis Tables, as returned by
        ``components``. Must include a ``"spine"`` key.

    Returns
    -------
    dict
        A dict of the form ``{entity_key: [component, ...]}`` where each
        component is a string (tag) or a single-key dict.
    """
    spine_df = spine.execute()
    id_to_key = (
        spine_df.drop_duplicates("entity_id")
        .set_index("entity_id")["entity_key"]
        .to_dict()
    )
    user_entity_ids = set(
        spine_df[~spine_df["filepath"].str.startswith("builtins")]["entity_id"].unique()
    )

    result: dict[str, list] = {}

    for comp_type, table in components.items():
        if comp_type == "spine":
            continue

        df = table.execute()
        if "entity_id" not in df.columns or "component_index" not in df.columns:
            continue

        for _, row in df.iterrows():
            entity_id = row["entity_id"]
            if entity_id not in user_entity_ids:
                continue

            entity_key = id_to_key.get(entity_id, entity_id)
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

            result.setdefault(entity_key, []).append(
                (int(row["component_index"]), entry)
            )

    return {
        ekey: [e for _, e in sorted(entries, key=lambda x: x[0])]
        for ekey, entries in result.items()
    }


def exported_manifest_filepaths(entity_first_data: dict) -> list[str]:
    """Save entity_first_data to yaml file(s) and return a list of strings
    with the filepath(s).

    Parameters
    ----------
    entity_first_data : dict
        The entity-centered structure, as returned by ``entity_first_data``.

    Returns
    -------
    list[str]
        The saved filepaths.
    """
    return entity_first_data