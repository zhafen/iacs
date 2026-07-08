"""Hamilton DAG for the todo audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry


INPUT_COMPONENT_TYPES = ["todo"]


@extract_fields({"todo_component": ir.Table})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow.

    The ``todo`` component is extracted as ``todo_component`` to avoid a name
    collision with the ``todo`` output node produced by this DAG.
    """
    return {"todo_component": registry.get("todo")}



def todo_table(todo_component: ir.Table) -> ibis.expr.types.Table | None:
    """Get the todo component table, or None if no todos exist."""
    if todo_component.count().execute() == 0:
        return None
    return todo_component


def todo(todo_table: ibis.expr.types.Table | None) -> ibis.expr.types.Table:
    """Return outstanding todos. Empty table means no todos."""
    if todo_table is None:
        return ibis.memtable(
            {"entity_id": [], "value": []},
            schema={"entity_id": "string", "value": "string"},
        )
    if "value" in todo_table.columns:
        return todo_table.select("entity_id", "value")
    return todo_table.select("entity_id").mutate(value=ibis.literal(""))


def updated_registry(registry: Registry, todo: ibis.expr.types.Table) -> Registry:
    """Store the todo audit result as a component in the registry."""
    registry.update({"todo": todo})
    return registry


FINAL_VAR = "todo"
