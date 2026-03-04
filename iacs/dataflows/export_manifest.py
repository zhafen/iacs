"""Hamilton DAG for converting component-centered registry data back to entity-centered manifest data."""

import pandas as pd

from ..registry import Registry


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


def manifests(entity_first_data: dict) -> dict:
    """Convert entity-first data into per-file manifest dicts ready for YAML serialization.

    Parameters
    ----------
    entity_first_data : dict
        The nested entity-first structure keyed by filepath, as returned by
        ``entity_first_data``.

    Returns
    -------
    dict
        A dict mapping each filepath to its top-level entity dict, matching
        the structure of the original manifest YAML files.
    """
    return
