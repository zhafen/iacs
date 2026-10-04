"""Hamilton DAG for the traceability audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from emc2p.registry import Registry


INPUT_COMPONENT_TYPES = ["requirement_priority", "solution", "entity_id"]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow."""
    return {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES}


def all_entities(entity_id: ir.Table) -> ibis.expr.types.Table:
    """Collect all unique entity IDs from the entity_id component."""
    return entity_id.select(entity_id["value"].name("entity_id")).distinct()


def req_entities(requirement_priority: ir.Table, solution: ir.Table) -> ibis.expr.types.Table:
    """Entities that count as a requirement.

    Union of two independent ways an entity earns that status, matching
    the two conventions documented on the ``requirement``/``solution``
    component types in emc2p's builtins/auditing.yaml: carrying a
    ``requirement_priority`` tag (scored), or simply being the target
    (``value_eid``) of a ``solution`` relation (relation-only, no tag or
    score needed).
    """
    tagged = requirement_priority.select("entity_id").distinct()
    if "value_eid" not in solution.columns:
        return tagged
    solved = (
        solution
        .filter(ibis._.value_eid.notnull())
        .select(ibis._.value_eid.name("entity_id"))
        .distinct()
    )
    return tagged.union(solved).distinct()


def solution_entities(solution: ir.Table) -> ibis.expr.types.Table:
    """Get entities with solution components."""
    return solution.select("entity_id").distinct()


def orphan_entities(
    all_entities: ibis.expr.types.Table,
    req_entities: ibis.expr.types.Table,
    solution_entities: ibis.expr.types.Table,
) -> ibis.expr.types.Table:
    """Find entities that don't trace to any requirement."""
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


FINAL_VAR = "traceability"
