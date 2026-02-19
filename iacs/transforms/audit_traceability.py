"""Hamilton DAG for the traceability audit."""

import ibis

from iacs.registry import Registry


def all_entities(registry: Registry) -> ibis.expr.types.Table | None:
    """Collect all unique entity IDs across all component types."""
    if not registry.component_types:
        return None
    tables = [
        registry.view(ct).select("entity_id").distinct()
        for ct in registry.component_types
    ]
    return ibis.union(*tables).distinct()


def req_entities(registry: Registry) -> ibis.expr.types.Table:
    """Get entities with requirement components."""
    if "requirement" in registry.component_types:
        return registry.view("requirement").select("entity_id").distinct()
    return ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})


def solution_entities(registry: Registry) -> ibis.expr.types.Table:
    """Get entities with solution of components."""
    if "solution of" in registry.component_types:
        return registry.view("solution of").select("entity_id").distinct()
    return ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})


def orphan_entities(
    all_entities: ibis.expr.types.Table | None,
    req_entities: ibis.expr.types.Table,
    solution_entities: ibis.expr.types.Table,
) -> ibis.expr.types.Table:
    """Find entities that don't trace to any requirement."""
    if all_entities is None:
        return ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    return all_entities.filter(
        ~all_entities.entity_id.isin(req_entities.entity_id)
        & ~all_entities.entity_id.isin(solution_entities.entity_id)
    )


def traceability(orphan_entities: ibis.expr.types.Table) -> ibis.expr.types.Table:
    """Return orphan entities. Empty table means full traceability."""
    return orphan_entities.mutate(
        message=("Entity '" + orphan_entities.entity_id + "' does not trace to any requirement.")
    )
