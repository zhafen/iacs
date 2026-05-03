"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ...registry import Registry


@extract_fields({
    "requirement": ir.Table,
    "solution": ir.Table,
    "work_state": ir.Table,
})
def components(registry: Registry) -> dict:
    comps = dict(registry._components)
    if "requirement" not in comps:
        comps["requirement"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    if "solution" not in comps:
        comps["solution"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    if "work_state" not in comps:
        comps["work_state"] = ibis.memtable({"entity_id": []}, schema={"entity_id": "string"})
    return comps

def solution_with_state(solution: ir.Table, work_state: ir.Table) -> ir.Table:
    return

def requirement_coverage(requirement: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    return

def updated_registry(registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    registry.update({"requirement_coverage": requirement_coverage})
    return registry
