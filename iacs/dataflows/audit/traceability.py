"""Hamilton DAG for the traceability audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry


INPUT_COMPONENT_TYPES = ["requirement", "solution_of", "entity_id"]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow.

    ``solution_of`` is fetched as ``"solution of"`` from the registry because
    Hamilton node names cannot contain spaces.
    """
    result = {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES if ct != "solution_of"}
    result["solution_of"] = registry.get("solution of")
    return result


def all_entities(entity_id: ir.Table) -> ibis.expr.types.Table:
    """Collect all unique entity IDs from the entity_id component."""
    return entity_id.select(entity_id["value"].name("entity_id")).distinct()


def req_entities(requirement: ir.Table) -> ibis.expr.types.Table:
    """Get entities with requirement components."""
    return requirement.select("entity_id").distinct()


def solution_entities(solution_of: ir.Table) -> ibis.expr.types.Table:
    """Get entities with solution of components."""
    return solution_of.select("entity_id").distinct()


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
