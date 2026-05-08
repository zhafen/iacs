"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ...registry import Registry


@extract_fields({
    "requirement": ir.Table,
    "solution": ir.Table,
    "status": ir.Table,
})
def components(derived_registry: Registry) -> dict:
    comps = dict(derived_registry._components)
    if "requirement" not in comps:
        comps["requirement"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    if "solution" not in comps:
        comps["solution"] = ibis.memtable(
            {"entity_id": [], "value_entity_id": []},
            schema={"entity_id": "string", "value_entity_id": "string"},
        )
    if "status" not in comps:
        comps["status"] = ibis.memtable(
            {"entity_id": [], "value": []},
            schema={"entity_id": "string", "value": "string"},
        )
    return comps


def solution_with_state(solution: ir.Table, status: ir.Table) -> ir.Table:
    """Join solutions with their resolved requirement entity IDs and work state.

    solution.value_entity_id is populated by derive_components based on the entity_ref
    field declared for the solution component in builtins/components.yaml.
    """
    return (
        solution
        .left_join(status, solution.entity_id == status.entity_id)
        .select(
            solution.entity_id.name("solution"),
            solution.value_entity_id.name("entity_id"),
            status.value.name("solution_status"),
        )
    )


def requirement_coverage(requirement: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    """For each requirement, show which solution covers it and its status."""
    req = requirement.select("entity_id").distinct()
    return req.left_join(
        solution_with_state, req.entity_id == solution_with_state.entity_id
    ).select(
        req.entity_id,
        solution_with_state.solution,
        solution_with_state.solution_status,
    )


def updated_registry(derived_registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    derived_registry.update({"requirement_coverage": requirement_coverage})
    return derived_registry
