"""Hamilton DAG for the traceability audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry


@extract_fields({"requirement": ir.Table, "solution_of": ir.Table})
def components(registry: Registry) -> dict:
    """Give access to the components dict from the registry."""
    comps = dict(registry._components)
    if "requirement" not in comps:
        comps["requirement"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    comps["solution_of"] = comps.pop(
        "solution of",
        ibis.memtable({"entity_id": []}, schema={"entity_id": "string"}),
    )
    return comps


def all_entities(registry: Registry) -> ibis.expr.types.Table | None:
    """Collect all unique entity IDs across all component types."""
    tables = [
        registry._components[ct].select("entity_id").distinct()
        for ct in registry._components
        if isinstance(registry._components[ct], ibis.Table) and "entity_id" in registry._components[ct].columns
    ]
    if not tables:
        return None
    return ibis.union(*tables).distinct()


def req_entities(requirement: ir.Table) -> ibis.expr.types.Table:
    """Get entities with requirement components."""
    return requirement.select("entity_id").distinct()


def solution_entities(solution_of: ir.Table) -> ibis.expr.types.Table:
    """Get entities with solution of components."""
    return solution_of.select("entity_id").distinct()


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
