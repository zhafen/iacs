"""View helpers for building requirement tree data structures."""

from collections import defaultdict

import networkx as nx
import pandas as pd

from iacs.registrar import Registrar

# format_guide.yaml self-documents the EC format spec (see
# iacs.commands.build_format_description) using the same "requirement"
# tagging convention as real project data, but it isn't project data — it
# ships alongside a manifest purely for the describe_format tool. Its
# entities are excluded from requirement trees so format-spec constraints
# don't get mixed in with the project's actual requirements.
_FORMAT_GUIDE_BASENAME = "format_guide.yaml"


def _non_format_guide_ids(entity_ids_pd: pd.DataFrame, ids: set) -> set:
    """Return ``ids`` with any entity sourced from format_guide.yaml removed."""
    if "filepath" not in entity_ids_pd.columns:
        return ids
    excluded = set(
        entity_ids_pd.loc[
            entity_ids_pd["filepath"].astype(str).str.endswith(_FORMAT_GUIDE_BASENAME),
            "value",
        ]
    )
    return ids - excluded


def _requirement_node(node_id, children_map: dict, id_to_key: dict, id_to_priority: dict) -> dict:
    """Recursively build a {name, priority, children} dict for one subtree."""
    node = {
        "name": id_to_key.get(node_id, node_id[:8]),
        "priority": id_to_priority.get(node_id, 0.5),
    }
    children = sorted(
        children_map.get(node_id, []),
        key=lambda c: id_to_priority.get(c, 0.5),
        reverse=True,
    )
    if children:
        node["children"] = [
            _requirement_node(c, children_map, id_to_key, id_to_priority) for c in children
        ]
    return node


def build_requirement_tree(registrar: Registrar, ancestor_key: str) -> dict:
    """Return nested {name, priority, children} dict for D3 hierarchy.

    Args:
        registrar: A Registrar instance with loaded registry data.
        ancestor_key: The entity_key of the root entity for the tree.

    Returns:
        A nested dict with keys 'name', 'priority', and optionally 'children'.

    Raises:
        ValueError: If no entity is found with the given ancestor_key.
    """
    entity_ids_pd = registrar.get("entity_id").to_pandas()
    parents_pd = registrar.get("parent").to_pandas()
    reqs_pd = registrar.get("requirement").to_pandas()

    id_to_key = entity_ids_pd.set_index("value")["entity_key"].to_dict()
    req_ids = _non_format_guide_ids(entity_ids_pd, set(reqs_pd["entity_id"].unique()))

    # Use max priority per entity (an entity may have multiple requirement rows)
    id_to_priority = reqs_pd.groupby("entity_id")["value"].max().to_dict()

    ancestor_rows = entity_ids_pd[entity_ids_pd["entity_key"] == ancestor_key]
    if ancestor_rows.empty:
        raise ValueError(f"No entity found with entity_key '{ancestor_key}'")
    ancestor_id = ancestor_rows.iloc[0]["value"]

    # Build full graph and find req descendants
    G_full = nx.DiGraph()
    for _, row in parents_pd.iterrows():
        G_full.add_edge(row["parent_eid"], row["entity_id"])

    descendants = nx.descendants(G_full, ancestor_id) | {ancestor_id}
    req_nodes = (descendants & req_ids) | {ancestor_id}

    # Build children lookup restricted to req_nodes
    children_map = defaultdict(list)
    for _, row in parents_pd.iterrows():
        if row["parent_eid"] in req_nodes and row["entity_id"] in req_nodes:
            children_map[row["parent_eid"]].append(row["entity_id"])

    return _requirement_node(ancestor_id, children_map, id_to_key, id_to_priority)


def build_requirement_forest(registrar: Registrar) -> dict:
    """Return nested {name, priority, children} dict covering every requirement.

    Unlike ``build_requirement_tree``, no ``ancestor_key`` is needed: root
    requirement entities (those with no requirement-typed ancestor) are
    auto-detected. A single root is returned directly; multiple roots are
    wrapped as children of a synthetic "Requirements" node so the result is
    always one D3-hierarchy-compatible tree.

    Args:
        registrar: A Registrar instance with loaded registry data.

    Returns:
        A nested dict with keys 'name', 'priority', and optionally
        'children'. A childless "Requirements" node if there are no
        requirements at all.
    """
    entity_ids_pd = registrar.get("entity_id").to_pandas()
    parents_pd = registrar.get("parent").to_pandas()
    reqs_pd = registrar.get("requirement").to_pandas()

    req_ids = _non_format_guide_ids(entity_ids_pd, set(reqs_pd["entity_id"].unique()))
    if not req_ids:
        return {"name": "Requirements", "priority": None}

    id_to_key = entity_ids_pd.set_index("value")["entity_key"].to_dict()
    id_to_priority = reqs_pd.groupby("entity_id")["value"].max().to_dict()

    graph = nx.DiGraph()
    for _, row in parents_pd.iterrows():
        graph.add_edge(row["parent_eid"], row["entity_id"])

    children_map = defaultdict(list)
    for _, row in parents_pd.iterrows():
        if row["parent_eid"] in req_ids and row["entity_id"] in req_ids:
            children_map[row["parent_eid"]].append(row["entity_id"])

    roots = [
        r for r in req_ids
        if not ((nx.ancestors(graph, r) if r in graph else set()) & req_ids)
    ]
    roots.sort(key=lambda r: id_to_priority.get(r, 0.5), reverse=True)

    trees = [_requirement_node(r, children_map, id_to_key, id_to_priority) for r in roots]
    if len(trees) == 1:
        return trees[0]
    return {"name": "Requirements", "priority": None, "children": trees}
