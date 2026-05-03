"""Hamilton DAG for the todo audit."""

import ibis

from iacs.registry import Registry


def components(registry: Registry) -> dict:
    """Give access to the components dict from the registry."""
    return registry._components


def todo_table(components: dict) -> ibis.expr.types.Table | None:
    """Get the todo component table, or None if no todos exist."""
    if "todo" not in components:
        return None
    table = components["todo"]
    if table.count().execute() == 0:
        return None
    return table


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
