"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from emc2p.registry import Registry


INPUT_COMPONENT_TYPES = ["requirement_priority", "solution", "status"]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow."""
    return {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES}


def solution_with_state(solution: ir.Table, status: ir.Table) -> ir.Table:
    """Join solutions with their resolved requirement entity IDs and work state.

    solution.value_eid is populated by derive_components based on the entity_ref
    field declared for the solution component in builtins/components.yaml.
    """
    if "value_eid" not in solution.columns:
        return ibis.memtable(
            [],
            schema={"solution_eid": "string", "entity_id": "string", "solution_status": "string"},
        )
    status_for_join = status.rename({"status_eid": "entity_id", "solution_status": "value"})
    return (
        solution
        .left_join(status_for_join, solution.entity_id == status_for_join.status_eid)
        .select(
            ibis._.entity_id.name("solution_eid"),
            ibis._.value_eid.name("entity_id"),
            ibis._.solution_status,
        )
    )


def requirement_entities(requirement_priority: ir.Table, solution: ir.Table) -> ir.Table:
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


def requirement_coverage(requirement_entities: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    """For each requirement, show which solution covers it and its status."""
    req = requirement_entities
    return req.left_join(solution_with_state, "entity_id").select(
        ibis._.entity_id,
        ibis._.solution_eid,
        ibis._.solution_status,
    )


def updated_registry(registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    registry.update({"requirement_coverage": requirement_coverage})
    return registry


FINAL_VAR = "requirement_coverage"
