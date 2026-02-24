"""Hamilton DAG for the requirement coverage audit."""

import ibis

from iacs.registry import Registry


def requirement_entities(registry: Registry) -> ibis.expr.types.Table | None:
    """Get unique requirement entity IDs, or None if no requirements exist."""
    if "requirement" not in registry.component_types:
        return None
    req_table = registry.view("requirement")
    reqs = req_table.select("entity_id").distinct()
    if reqs.count().execute() == 0:
        return None
    return reqs


def parents_with_req_children(
    registry: Registry, requirement_entities: ibis.expr.types.Table | None
) -> ibis.expr.types.Table:
    """Find requirement entities that have child requirements."""
    empty = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    if requirement_entities is None:
        return empty
    if "parent" not in registry.component_types:
        return empty
    parent_table = registry.view("parent")
    req_children = parent_table.filter(
        parent_table.entity_id.isin(requirement_entities.entity_id)
    )
    return (
        req_children.select(entity_id=req_children.target)
        .filter(lambda t: t.entity_id.isin(requirement_entities.entity_id))
        .distinct()
    )


def solved_requirements(registry: Registry) -> ibis.expr.types.Table:
    """Get entity IDs that have been solved."""
    empty = ibis.memtable({"solved_id": []}, schema={"solved_id": "string"})
    if "solution of" not in registry.component_types:
        return empty
    solution_table = registry.view("solution of")
    if "value" not in solution_table.columns:
        return empty
    return solution_table.select(solved_id=solution_table.value).distinct()


def uncovered_requirements(
    requirement_entities: ibis.expr.types.Table | None,
    parents_with_req_children: ibis.expr.types.Table,
    solved_requirements: ibis.expr.types.Table,
) -> ibis.expr.types.Table:
    """Find requirements that have no solution and no children."""
    if requirement_entities is None:
        return ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    merged = requirement_entities.left_join(
        solved_requirements,
        requirement_entities.entity_id == solved_requirements.solved_id,
    )
    return merged.filter(
        merged.solved_id.isnull()
        & ~merged.entity_id.isin(parents_with_req_children.entity_id)
    ).select("entity_id")


def requirement_coverage(
    registry: Registry, uncovered_requirements: ibis.expr.types.Table
) -> ibis.expr.types.Table:
    """Return uncovered requirements with context columns. Empty table means all covered."""
    result = uncovered_requirements
    if "id" in registry.component_types:
        id_table = registry.view("id")
        cols = [c for c in ["key", "path"] if c in id_table.columns]
        if cols:
            id_table = id_table.select("entity_id", *cols)
            result = result.left_join(
                id_table, "entity_id"
            ).select(result.entity_id, *[id_table[c] for c in cols])
    if "description" in registry.component_types:
        desc_table = registry.view("description").select("entity_id", description="value")
        result = result.left_join(
            desc_table, "entity_id"
        ).select(*[result[c] for c in result.columns], desc_table.description)
    if "requirement" in registry.component_types:
        req_table = registry.view("requirement")
        if "priority" in req_table.columns:
            req_table = req_table.select("entity_id", "priority")
            result = result.left_join(
                req_table, "entity_id"
            ).select(*[result[c] for c in result.columns], req_table.priority)
    return result
