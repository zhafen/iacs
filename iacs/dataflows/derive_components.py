"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.
"""

import networkx as nx
import pandas as pd

from iacs.registry import Registry
from iacs.utils import candidate_entity_ids


def field_types_with_entity_ref(validated_registry: Registry) -> dict[str, list[str]]:
    """Return a mapping of component_type -> [field_names] for entity_ref fields.

    Parameters
    ----------
    validated_registry : Registry
        The validated registry.

    Returns
    -------
    dict[str, list[str]]
        E.g. ``{"solution": ["target"]}``
    """
    field_df = validated_registry._components["field"].to_pandas()
    entity_id_df = validated_registry._components["entity_id"].to_pandas()

    entity_ref_fields = field_df[field_df["type"] == "entity_ref"]
    id_to_key = entity_id_df.set_index("value")["entity_key"]

    result: dict[str, list[str]] = {}
    for _, row in entity_ref_fields.iterrows():
        comp_type = id_to_key.get(row["entity_id"])
        if comp_type:
            result.setdefault(comp_type, []).append(row["value"])
    return result


def components_with_resolved_paths(
    validated_registry: Registry,
    field_types_with_entity_ref: dict[str, list[str]],
) -> dict[str, pd.DataFrame]:
    """Resolve entity_ref fields in each component to entity IDs.

    For each (component_type, field_names) pair, adds a ``{field}_id`` column
    containing the resolved entity ID (or ``None`` if 0 or 2+ candidates match).

    Parameters
    ----------
    validated_registry : Registry
        The validated registry.
    field_types_with_entity_ref : dict[str, list[str]]
        Mapping of component_type -> list of field names with entity_ref type.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of component_type -> DataFrame with resolved ``{field}_id`` columns.
    """
    entity_id_df = validated_registry._components["entity_id"].to_pandas()

    result: dict[str, pd.DataFrame] = {}
    for comp_type, field_names in field_types_with_entity_ref.items():
        if comp_type not in validated_registry._components:
            continue
        df = validated_registry._components[comp_type].to_pandas()
        for field_name in field_names:
            if field_name not in df.columns:
                continue

            def resolve(val, _df=entity_id_df):
                if pd.isna(val):
                    return None
                candidates = candidate_entity_ids(str(val), _df)
                return candidates[0] if len(candidates) == 1 else None

            df[f"{field_name}_id"] = df[field_name].apply(resolve)
        result[comp_type] = df
    return result

def entity_depth(validated_registry: Registry) -> pd.DataFrame:
    """Compute the depth of each entity in the parent hierarchy.

    Depth is the length of the shortest path from any root node (an entity with
    no parent) to the entity.  Entities that appear only as roots have depth 0.

    Parameters
    ----------
    validated_registry : Registry
        The validated registry.

    Returns
    -------
    pd.DataFrame
        One row per entity with columns ``entity_id`` and ``depth``.
    """
    parents_df = validated_registry._components["parent"].to_pandas()

    # Directed graph: parent -> child (natural top-down direction)
    G = nx.DiGraph()
    G.add_edges_from(zip(parents_df["parent_id"], parents_df["entity_id"]))

    # Roots: nodes that appear only as parents, never as children
    roots = [n for n in G.nodes if G.in_degree(n) == 0]

    # Multi-source BFS from all roots gives minimum depth for every reachable node
    depths = nx.multi_source_dijkstra_path_length(G, roots)

    return pd.DataFrame(list(depths.items()), columns=["entity_id", "depth"])


def derived_registry(registry: Registry, components_with_resolved_paths: dict) -> Registry:
    registry.update(components_with_resolved_paths)
    return registry