"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from ...registry import Registry

@extract_fields({
    "requirement": ir.Table,
    "solution": ir.Table,
    "work_state": ir.Table,
})
def components(registry: Registry) -> dict:
    return registry._components

def solution_with_state(solution: ir.Table, work_state: ir.Table) -> ir.Table:
    return

def requirement_coverage(requirement: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    return

def updated_registry(registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    registry.update({"requirement_coverage": requirement_coverage})
    return registry
