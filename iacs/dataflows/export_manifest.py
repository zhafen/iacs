"""Hamilton DAG for converting component-centered registry data back to entity-centered manifest data."""

import ibis.expr.types as ir

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
    return


def entity_first_data(components: dict) -> dict:
    """Reconstruct the entity-centered nested dict from component tables.

    Inverts the transformation performed by ``load_manifest``: given the spine
    and per-component-type tables, rebuilds the nested ``{entity: [components]}``
    structure grouped by filepath.

    Parameters
    ----------
    components : dict
        Dict mapping component type names to ibis Tables, as returned by
        ``components``. Must include a ``"spine"`` key.

    Returns
    -------
    dict
        A dict of the form ``{filepath: {entity_path: [component, ...]}}``
        mirroring the structure of ``raw_entity_first_data`` in ``load_manifest``.
    """
    return


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
