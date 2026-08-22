"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.
"""

import networkx as nx
import pandas as pd
from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir

from emc2p.registry import Registry
from emc2p.utils import candidate_entity_ids, non_format_guide_ids


INPUT_COMPONENT_TYPES = [
    "entity_id", "parent", "requirement_priority", "impact", "cost", "impact_budget", "cost_budget",
]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow."""
    return {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES}


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


def normalized_cost_sum(parent: ir.Table, cost: ir.Table, cost_budget: ir.Table) -> pd.DataFrame:
    """Sum normalized cost for each entity and all its descendants, grouped by schedule.

    Each cost row's value is weighted by the ``normalized_value_per_unit`` of
    the matching ``cost_budget`` entry for its ``type`` (defaulting to 1 when
    no budget is defined for that type) before being summed. For each entity
    that either has cost itself or is an ancestor of one that does, sums
    normalized cost values across the subtree rooted at that entity. Results
    are grouped by schedule.

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.
    cost : ir.Table
        The cost component table from the registry.
    cost_budget : ir.Table
        The cost_budget component table from the registry.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, schedule, value. One row per (entity_id, schedule)
        combination, where value is already budget-weighted.
    """
    cost_df = cost.to_pandas()
    required_cols = {"entity_id", "type", "value"}
    if not required_cols.issubset(cost_df.columns) or cost_df.empty:
        return pd.DataFrame(columns=["entity_id", "schedule", "value"])

    cost_df = cost_df.copy()
    if "schedule" in cost_df.columns:
        cost_df["schedule"] = cost_df["schedule"].replace("", pd.NA)
    else:
        cost_df["schedule"] = pd.NA
    budget_df = cost_budget.to_pandas()
    rate = (
        budget_df.set_index("value")["normalized_value_per_unit"]
        if not budget_df.empty
        else pd.Series(dtype=float)
    )
    weight = cost_df["type"].map(rate).fillna(1.0)
    cost_df["value"] = pd.to_numeric(cost_df["value"], errors="coerce") * weight
    parent_df = parent.to_pandas()

    # Directed graph: parent -> child
    G = nx.DiGraph()
    G.add_edges_from(zip(parent_df["parent_eid"], parent_df["entity_id"]))

    entities_with_cost = set(cost_df["entity_id"])
    # Only compute for entities that have cost somewhere in their subtree
    candidate_entities = {
        ancestor
        for eid in entities_with_cost
        for ancestor in (nx.ancestors(G, eid) if eid in G else set())
    } | entities_with_cost

    rows = []
    for entity_id in candidate_entities:
        subtree = (nx.descendants(G, entity_id) if entity_id in G else set()) | {entity_id}
        sub_cost = cost_df[cost_df["entity_id"].isin(subtree)]
        if sub_cost.empty:
            continue
        grouped = (
            sub_cost
            .groupby("schedule", dropna=False)["value"]
            .sum()
            .reset_index()
        )
        grouped.insert(0, "entity_id", entity_id)
        rows.append(grouped)

    if not rows:
        return pd.DataFrame(columns=["entity_id", "schedule", "value"])

    return pd.concat(rows, ignore_index=True)


def normalized_cost_total(normalized_cost_sum: pd.DataFrame, cost_time_period: str = "28 days") -> pd.DataFrame:
    """Convert normalized_cost_sum into a single total cost value per entity for a given time period.

    One-time costs (no schedule) are counted once. Recurring costs are
    multiplied by how many times they occur within ``cost_time_period``.
    All values are summed across schedules into a single number per entity.

    Parameters
    ----------
    normalized_cost_sum : pd.DataFrame
        Output of :func:`normalized_cost_sum`: columns entity_id, schedule, value.
    cost_time_period : str
        Duration string for the time window accepted by ``pd.Timedelta``,
        e.g. ``"28 days"`` or ``"90 days"``. Defaults to ``"28 days"`` (4 weeks).
        Common schedule aliases ("weekly", "daily", "monthly") are also accepted
        as schedule values inside ``normalized_cost_sum``.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, value. One row per entity with total normalized
        cost over the period, including its full descendant subtree.
    """
    if normalized_cost_sum.empty:
        return pd.DataFrame(columns=["entity_id", "value"])

    time_period = pd.Timedelta(cost_time_period)

    _SCHEDULE_ALIASES = {"weekly": "7 days", "daily": "1 day", "monthly": "30 days"}

    def _parse_schedule(schedule):
        if pd.isna(schedule):
            return None
        s = str(schedule).strip().lower()
        s = _SCHEDULE_ALIASES.get(s, s)
        return pd.Timedelta(s)

    df = normalized_cost_sum.copy()
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


def priority_product(parent: ir.Table, entity_id: ir.Table, requirement_priority: ir.Table) -> pd.DataFrame:
    """Compute the product of requirement priorities for an entity and its ancestors.

    For each entity that has a requirement_priority component itself or has at least
    one ancestor with a requirement_priority component, multiplies together the
    priority values of the entity and all its requirement_priority ancestors.

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.
    entity_id : ir.Table
        The entity_id component table from the registry.
    requirement_priority : ir.Table
        The requirement_priority component table from the registry.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, priority_product.  One row per entity that has
        a requirement_priority component or at least one ancestor with a
        requirement_priority component.
    """
    req_df = requirement_priority.to_pandas()
    if req_df.empty or "value" not in req_df.columns:
        return pd.DataFrame(columns=["entity_id", "priority_product"])

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


def impact_from_requirement(requirement_priority: ir.Table, entity_id: ir.Table) -> pd.DataFrame:
    """Synthesize impact rows from each requirement's priority value.

    ``requirement_priority`` is schema-declared as a child of ``impact`` and
    its ``value`` field is documented as "the priority/impact score for the
    requirement", so a requirement's priority doubles as its impact score
    without needing separately-authored impact data. format_guide.yaml's
    self-documentation entities (which also carry ``requirement_priority``
    tags to describe the EC format spec itself) are excluded, since they
    aren't project data.

    Parameters
    ----------
    requirement_priority : ir.Table
        The requirement_priority component table from the registry.
    entity_id : ir.Table
        The entity spine table, used to exclude format_guide.yaml entities.

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, value, type ("impact"). One row per requirement
        entity outside of format_guide.yaml.
    """
    req_df = requirement_priority.to_pandas()
    if req_df.empty or "value" not in req_df.columns:
        return pd.DataFrame(columns=["entity_id", "value", "type"])

    eid_df = entity_id.to_pandas()
    keep_ids = non_format_guide_ids(eid_df, set(req_df["entity_id"].unique()))
    req_df = req_df[req_df["entity_id"].isin(keep_ids)]
    if req_df.empty:
        return pd.DataFrame(columns=["entity_id", "value", "type"])

    result = req_df.groupby("entity_id")["value"].max().reset_index()
    result["type"] = "impact"
    return result[["entity_id", "value", "type"]]


def resolved_impact_cost(
    impact: ir.Table,
    impact_budget: ir.Table,
    impact_from_requirement: pd.DataFrame,
    normalized_cost_total: pd.DataFrame,
) -> pd.DataFrame:
    """Compute normalized impact and cost totals for each entity.

    Each impact row's value is weighted by the ``normalized_value_per_unit``
    of the matching ``impact_budget`` entry for its ``type`` (defaulting to 1
    when no budget is defined for that type), then summed per entity. Impact
    rows are the union of any directly-authored ``impact`` components and
    those synthesized from requirement priorities (see
    ``impact_from_requirement``). Cost comes from ``normalized_cost_total``,
    which is already budget-weighted, rolled up across each entity's full
    descendant subtree, and schedule-adjusted — so a container entity's cost
    reflects everything needed to fulfill it, not just its own direct cost
    components.

    Parameters
    ----------
    impact : ir.Table
        The impact component table from the registry.
    impact_budget : ir.Table
        The impact_budget component table from the registry.
    impact_from_requirement : pd.DataFrame
        Impact rows synthesized from requirement priorities.
    normalized_cost_total : pd.DataFrame
        Per-entity subtree-summed, budget-weighted cost totals (see
        ``normalized_cost_total``).

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, impact, cost, diff, ratio. One row per entity that
        has at least one impact or cost (own or via a descendant) component.
    """
    def _normalized_sum(df: pd.DataFrame, budget_df: pd.DataFrame) -> pd.Series:
        if df.empty or "value" not in df.columns or "type" not in df.columns:
            return pd.Series(dtype=float)
        rate = (
            budget_df.set_index("value")["normalized_value_per_unit"]
            if not budget_df.empty
            else pd.Series(dtype=float)
        )
        weight = df["type"].map(rate).fillna(1.0)
        weighted = pd.to_numeric(df["value"], errors="coerce") * weight
        return weighted.groupby(df["entity_id"]).sum()

    impact_df = pd.concat([impact.to_pandas(), impact_from_requirement], ignore_index=True)
    impact_sum = _normalized_sum(impact_df, impact_budget.to_pandas())
    cost_sum = (
        normalized_cost_total.set_index("entity_id")["value"]
        if not normalized_cost_total.empty
        else pd.Series(dtype=float)
    )

    result = pd.DataFrame({"impact": impact_sum, "cost": cost_sum}).fillna(0.0)
    if result.empty:
        return pd.DataFrame(columns=["entity_id", "impact", "cost", "diff", "ratio"])

    result["diff"] = result["impact"] - result["cost"]
    result["ratio"] = result["impact"] / result["cost"]
    return result.rename_axis("entity_id").reset_index()[
        ["entity_id", "impact", "cost", "diff", "ratio"]
    ]


def derived_registry(
    registry: Registry,
    entity_depth: pd.DataFrame,
    normalized_cost_total: pd.DataFrame,
    priority_product: pd.DataFrame,
    resolved_impact_cost: pd.DataFrame,
) -> Registry:
    """Store all derived components back to the registry."""
    derived = {
        "entity_depth": entity_depth,
        "normalized_cost_total": normalized_cost_total,
        "priority_product": priority_product,
        "resolved_impact_cost": resolved_impact_cost,
    }
    registry.update({k: v for k, v in derived.items() if not v.empty})
    return registry


FINAL_VAR = "derived_registry"


