"""View helpers for building requirement tree data structures."""

from collections import defaultdict

import networkx as nx

from iacs.registrar import Registrar
from emc2p.utils import non_format_guide_ids


def _requirement_node(node_id, children_map: dict, id_to_key: dict, id_to_priority: dict) -> dict:
    """Recursively build a {name, priority, children} dict for one subtree.

    ``priority`` is None for a requirement that has no ``requirement_priority``
    score -- i.e. one recognized purely via the relation-only
    requirement/solution convention (see ``_requirement_entity_ids``) -- so a
    view can tell the two apart instead of a scored and an unscored
    requirement both silently reading as priority 0.5.
    """
    node = {
        "name": id_to_key.get(node_id, node_id[:8]),
        "priority": id_to_priority.get(node_id),
    }
    children = sorted(
        children_map.get(node_id, []),
        key=lambda c: id_to_priority.get(c, 0.5) if id_to_priority.get(c) is not None else 0.5,
        reverse=True,
    )
    if children:
        node["children"] = [
            _requirement_node(c, children_map, id_to_key, id_to_priority) for c in children
        ]
    return node


def _requirement_entity_ids(registrar: "Registrar", entity_ids_pd, reqs_pd) -> set:
    """IDs of entities that count as a requirement.

    Union of several independent ways an entity earns that status, matching
    the conventions documented on the ``requirement``/``solution`` component
    types in emc2p's builtins/auditing.yaml (pure_connection_architecture in
    iacs_meta_discussion.requirement_solution_modeling_discussion):

    - Tagged: it carries a ``requirement_priority`` component (a scored,
      standalone requirement; the older, now-deprecated convention).
    - Solved: it's the target (``value_eid``) of a ``solution`` component --
      some other entity solves it -- with no tag of its own.
    - Related: it's either side of a ``requirement`` component (the
      directed_relation inverse of ``solution``) -- the thing required
      (``entity_id``) or the thing requiring it (``value_eid``). Including
      both sides matters for a grouping entity with no solution or score of
      its own: it's required by its parent and requires its children, and
      needs to stay a tree node on both counts so its sub-requirements
      don't get wrongly promoted into disconnected roots.
    """
    tagged_ids = non_format_guide_ids(entity_ids_pd, set(reqs_pd["entity_id"].unique()))

    raw_relation_ids = set()
    solution_pd = registrar.get("solution").to_pandas()
    if "value_eid" in solution_pd.columns:
        raw_relation_ids |= set(solution_pd["value_eid"].dropna().unique())
    requirement_pd = registrar.get("requirement").to_pandas()
    if "value_eid" in requirement_pd.columns:
        raw_relation_ids |= set(requirement_pd["entity_id"].dropna().unique())
        raw_relation_ids |= set(requirement_pd["value_eid"].dropna().unique())

    relation_ids = non_format_guide_ids(entity_ids_pd, raw_relation_ids) if raw_relation_ids else set()
    return tagged_ids | relation_ids


def build_requirement_tree(registrar: Registrar, ancestor_key: str) -> dict:
    """Return nested {name, priority, children} dict for D3 hierarchy.

    Args:
        registrar: A Registrar instance with loaded registry data.
        ancestor_key: The display_key of the root entity for the tree.

    Returns:
        A nested dict with keys 'name', 'priority', and optionally 'children'.

    Raises:
        ValueError: If no entity is found with the given ancestor_key.
    """
    entity_ids_pd = registrar.get("entity_id").to_pandas()
    parents_pd = registrar.get("parent").to_pandas()
    reqs_pd = registrar.get("requirement_priority").to_pandas()

    id_to_key = entity_ids_pd.set_index("value")["display_key"].to_dict()
    req_ids = _requirement_entity_ids(registrar, entity_ids_pd, reqs_pd)

    # Use max priority per entity (an entity may have multiple requirement rows)
    id_to_priority = reqs_pd.groupby("entity_id")["value"].max().to_dict()

    ancestor_rows = entity_ids_pd[entity_ids_pd["display_key"] == ancestor_key]
    if ancestor_rows.empty:
        raise ValueError(f"No entity found with display_key '{ancestor_key}'")
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

    Unlike ``build_requirement_tree``, no ``ancestor_key`` is needed. If any
    entity carries a ``mission`` tag, the tree is scoped to only those
    entities' descendants — this is the normal case, since a project's
    solutions are typically authored as separate top-level entities not
    nested under its mission, and would otherwise each appear as their own
    disconnected root. Without any ``mission`` tag, root requirement
    entities (those with no requirement-tagged ancestor) are auto-detected
    instead, so the tree still degrades gracefully. A single root is
    returned directly; multiple roots are wrapped as children of a
    synthetic "Requirements" node so the result is always one
    D3-hierarchy-compatible tree.

    Args:
        registrar: A Registrar instance with loaded registry data.

    Returns:
        A nested dict with keys 'name', 'priority', and optionally
        'children'. A childless "Requirements" node if there are no
        requirements at all.
    """
    entity_ids_pd = registrar.get("entity_id").to_pandas()
    parents_pd = registrar.get("parent").to_pandas()
    reqs_pd = registrar.get("requirement_priority").to_pandas()
    mission_pd = registrar.get("mission").to_pandas()

    req_ids = _requirement_entity_ids(registrar, entity_ids_pd, reqs_pd)
    if not req_ids:
        return {"name": "Requirements", "priority": None}

    id_to_key = entity_ids_pd.set_index("value")["display_key"].to_dict()
    id_to_priority = reqs_pd.groupby("entity_id")["value"].max().to_dict()

    graph = nx.DiGraph()
    for _, row in parents_pd.iterrows():
        graph.add_edge(row["parent_eid"], row["entity_id"])

    mission_ids = non_format_guide_ids(entity_ids_pd, set(mission_pd["entity_id"].unique()))

    if mission_ids:
        # Scoped mode: only mission entities are roots, and only their
        # descendants (that are themselves requirements) are included —
        # solutions elsewhere in the manifest are out of scope entirely.
        roots = sorted(mission_ids, key=lambda r: id_to_priority.get(r, 0.5), reverse=True)
        node_ids = set(roots)
        for r in roots:
            node_ids |= (nx.descendants(graph, r) if r in graph else set()) & req_ids
    else:
        # Auto-detect mode: every requirement with no requirement-tagged
        # ancestor becomes its own root.
        roots = [
            r for r in req_ids
            if not ((nx.ancestors(graph, r) if r in graph else set()) & req_ids)
        ]
        roots.sort(key=lambda r: id_to_priority.get(r, 0.5), reverse=True)
        node_ids = req_ids

    children_map = defaultdict(list)
    for _, row in parents_pd.iterrows():
        if row["parent_eid"] in node_ids and row["entity_id"] in node_ids:
            children_map[row["parent_eid"]].append(row["entity_id"])

    trees = [_requirement_node(r, children_map, id_to_key, id_to_priority) for r in roots]
    if len(trees) == 1:
        return trees[0]
    return {"name": "Requirements", "priority": None, "children": trees}
