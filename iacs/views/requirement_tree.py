"""View helpers for building requirement tree data structures."""

from collections import defaultdict

import networkx as nx

from iacs.registrar import Registrar


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
    req_ids = set(reqs_pd["entity_id"].unique())

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

    def build_tree(node_id):
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
            node["children"] = [build_tree(c) for c in children]
        return node

    return build_tree(ancestor_id)
