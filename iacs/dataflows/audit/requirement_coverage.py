"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ...registry import Registry


@extract_fields({
    "requirement": ir.Table,
    "solution": ir.Table,
    "work_state": ir.Table,
    "entity_id_table": ir.Table,
})
def components(registry: Registry) -> dict:
    comps = dict(registry._components)
    if "requirement" not in comps:
        comps["requirement"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    if "solution" not in comps:
        comps["solution"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    comps["work_state"] = comps.get(
        "status",
        ibis.memtable({"entity_id": [], "value": []}, schema={"entity_id": "string", "value": "string"}),
    )
    comps["entity_id_table"] = comps.get(
        "entity_id",
        ibis.memtable({"value": [], "path": []}, schema={"value": "string", "path": "string"}),
    )
    return comps


def solution_with_state(solution: ir.Table, work_state: ir.Table, entity_id_table: ir.Table) -> ir.Table:
    """Join solutions with their resolved requirement entity IDs and work state."""
    eid = entity_id_table.mutate(
        entity_path=entity_id_table.path.split(":")[1]
    ).select(
        entity_id_table.value.name("req_entity_id"),
        ibis._.entity_path,
    )

    sol_resolved = solution.left_join(eid, solution.value == eid.entity_path).select(
        solution.entity_id.name("solution_entity_id"),
        eid.req_entity_id,
    )

    status = work_state.select(
        work_state.entity_id.name("sol_entity_id"),
        work_state.value.name("status_value"),
    )

    return sol_resolved.left_join(
        status, sol_resolved.solution_entity_id == status.sol_entity_id
    ).select("solution_entity_id", "req_entity_id", "status_value")


def requirement_coverage(requirement: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    """For each requirement, show which solution covers it and its status."""
    req = requirement.select("entity_id").distinct()

    sol = solution_with_state.select(
        solution_with_state.solution_entity_id.name("solution"),
        solution_with_state.req_entity_id.name("coverage_key"),
        solution_with_state.status_value.name("solution_status"),
    )

    return req.left_join(sol, req.entity_id == sol.coverage_key).select(
        req.entity_id,
        sol.solution,
        sol.solution_status,
    )


def updated_registry(registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    registry.update({"requirement_coverage": requirement_coverage})
    return registry
