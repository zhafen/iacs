"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.
"""

import networkx as nx
import pandas as pd
from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir

from iacs.registry import Registry
from iacs.utils import candidate_entity_ids


@extract_fields(dict(entity_id=ir.Table, parent=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in the registry."""
    return registry._components


def entity_depth(parent: ir.Table) -> pd.DataFrame:
    """Compute the depth of each entity in the parent hierarchy.

    Depth is the length of the shortest path from any root node (an entity with
    no parent) to the entity.  Entities that appear only as roots have depth 0.

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.

    Returns
    -------
    pd.DataFrame
        One row per entity with columns ``entity_id`` and ``depth``.
    """
    parents_df = parent.to_pandas()

    # Directed graph: parent -> child (natural top-down direction)
    G = nx.DiGraph()
    G.add_edges_from(zip(parents_df["parent_eid"], parents_df["entity_id"]))

    # Roots: nodes that appear only as parents, never as children
    roots = [n for n in G.nodes if G.in_degree(n) == 0]

    # Multi-source BFS from all roots gives minimum depth for every reachable node
    depths = nx.multi_source_dijkstra_path_length(G, roots)

    return pd.DataFrame(list(depths.items()), columns=["entity_id", "depth"])


def effort_sum(parent: ir.Table, components: dict) -> pd.DataFrame:
    """Sum effort for each entity and all its descendants, grouped by schedule and unit.

    For each entity that either has effort itself or is an ancestor of one that
    does, sums all effort values across the subtree rooted at that entity.
    Results are grouped by (schedule, unit).

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.
    components : dict
        The full components dict from the registry.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, schedule, unit, value.  One row per
        (entity_id, schedule, unit) combination.
    """
    if "effort" not in components:
        return pd.DataFrame(columns=["entity_id", "schedule", "unit", "value"])

    effort_df = components["effort"].to_pandas()
    required_cols = {"entity_id", "schedule", "unit", "value"}
    if not required_cols.issubset(effort_df.columns):
        return pd.DataFrame(columns=["entity_id", "schedule", "unit", "value"])
    effort_df["schedule"] = effort_df["schedule"].replace("", pd.NA)
    effort_df["value"] = pd.to_numeric(effort_df["value"], errors="coerce")
    parent_df = parent.to_pandas()

    # Directed graph: parent -> child
    G = nx.DiGraph()
    G.add_edges_from(zip(parent_df["parent_eid"], parent_df["entity_id"]))

    entities_with_effort = set(effort_df["entity_id"])
    # Only compute for entities that have effort somewhere in their subtree
    candidate_entities = {
        ancestor
        for eid in entities_with_effort
        for ancestor in (nx.ancestors(G, eid) if eid in G else set())
    } | entities_with_effort

    rows = []
    for entity_id in candidate_entities:
        subtree = (nx.descendants(G, entity_id) if entity_id in G else set()) | {entity_id}
        sub_effort = effort_df[effort_df["entity_id"].isin(subtree)]
        if sub_effort.empty:
            continue
        grouped = (
            sub_effort
            .groupby(["schedule", "unit"], dropna=False)["value"]
            .sum()
            .reset_index()
        )
        grouped.insert(0, "entity_id", entity_id)
        rows.append(grouped)

    if not rows:
        return pd.DataFrame(columns=["entity_id", "schedule", "unit", "value"])

    return pd.concat(rows, ignore_index=True)


def effort_total(effort_sum: pd.DataFrame, effort_time_period: str = "28 days") -> pd.DataFrame:
    """Convert effort_sum into a single total effort value per entity for a given time period.

    One-time efforts (no schedule) are counted once. Recurring efforts are
    multiplied by how many times they occur within ``effort_time_period``.
    All values are summed across schedules and units into a single number per entity.

    Parameters
    ----------
    effort_sum : pd.DataFrame
        Output of :func:`effort_sum`: columns entity_id, schedule, unit, value.
    effort_time_period : str
        Duration string for the time window accepted by ``pd.Timedelta``,
        e.g. ``"28 days"`` or ``"90 days"``. Defaults to ``"28 days"`` (4 weeks).
        Common schedule aliases ("weekly", "daily", "monthly") are also accepted
        as schedule values inside ``effort_sum``.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, value. One row per entity with total effort over the period.
    """
    if effort_sum.empty:
        return pd.DataFrame(columns=["entity_id", "value"])

    time_period = pd.Timedelta(effort_time_period)

    _SCHEDULE_ALIASES = {"weekly": "7 days", "daily": "1 day", "monthly": "30 days"}

    def _parse_schedule(schedule):
        if pd.isna(schedule):
            return None
        s = str(schedule).strip().lower()
        s = _SCHEDULE_ALIASES.get(s, s)
        return pd.Timedelta(s)

    df = effort_sum.copy()
    df["_period"] = df["schedule"].apply(_parse_schedule)
    df["_multiplier"] = df["_period"].apply(
        lambda p: (time_period / p) if not pd.isna(p) else 1.0
    )
    df["_weighted"] = df["value"] * df["_multiplier"]

    result = (
        df.groupby("entity_id")["_weighted"]
        .sum()
        .reset_index()
        .rename(columns={"_weighted": "value"})
    )
    return result


def priority_product(parent: ir.Table, entity_id: ir.Table, components: dict) -> pd.DataFrame:
    """Compute the product of requirement priorities for an entity and its ancestors.

    For each entity that has a requirement component itself or has at least one
    ancestor with a requirement component, multiplies together the priority values
    of the entity and all its requirement ancestors.

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.
    entity_id : ir.Table
        The entity_id component table from the registry.
    components : dict
        The full components dict from the registry.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, priority_product.  One row per entity that has
        a requirement component or at least one ancestor with a requirement component.
    """
    if "requirement" not in components:
        return pd.DataFrame(columns=["entity_id", "priority_product"])

    req_df = components["requirement"].to_pandas()
    parent_df = parent.to_pandas()

    req_priority = req_df.set_index("entity_id")["value"]

    # Directed graph: parent -> child
    G = nx.DiGraph()
    G.add_edges_from(zip(parent_df["parent_eid"], parent_df["entity_id"]))

    entity_id_df = entity_id.to_pandas()
    all_entity_ids = entity_id_df["value"].tolist()

    rows = []
    for eid in all_entity_ids:
        ancestors = nx.ancestors(G, eid) if eid in G else set()
        req_nodes = [a for a in ancestors if a in req_priority.index]
        if eid in req_priority.index:
            req_nodes.append(eid)
        if not req_nodes:
            continue
        product = 1.0
        for req_id in req_nodes:
            priority = req_priority[req_id]
            if pd.notna(priority) and priority != "":
                product *= float(priority)
        rows.append({"entity_id": eid, "priority_product": product})

    return pd.DataFrame(rows, columns=["entity_id", "priority_product"])


def derived_registry(
    registry: Registry,
    entity_depth: pd.DataFrame,
    effort_total: pd.DataFrame,
    priority_product: pd.DataFrame,
) -> Registry:
    """Store all derived components back to the registry."""
    derived = {
        "entity_depth": entity_depth,
        "effort_total": effort_total,
        "priority_product": priority_product,
    }
    registry.update({k: v for k, v in derived.items() if not v.empty})
    return registry


