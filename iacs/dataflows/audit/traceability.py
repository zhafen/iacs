"""Hamilton DAG for the traceability audit."""

import ibis

from iacs.registry import Registry


def components(registry: Registry) -> dict:
    """Give access to the components dict from the registry."""
    return registry._components


def all_entities(components: dict) -> ibis.expr.types.Table | None:
    """Collect all unique entity IDs across all component types."""
    tables = [
        components[ct].select("entity_id").distinct()
        for ct in components
        if isinstance(components[ct], ibis.Table)
    ]
    if not tables:
        return None
    return ibis.union(*tables).distinct()


def req_entities(components: dict) -> ibis.expr.types.Table:
    """Get entities with requirement components."""
    if "requirement" in components:
        return components["requirement"].select("entity_id").distinct()
    return ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})


def solution_entities(components: dict) -> ibis.expr.types.Table:
    """Get entities with solution of components."""
    if "solution of" in components:
        return components["solution of"].select("entity_id").distinct()
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


def updated_registry(registry: Registry, traceability: ibis.expr.types.Table) -> Registry:
    """Store the traceability audit result as a component in the registry."""
    registry.update({"traceability": traceability})
    return registry
