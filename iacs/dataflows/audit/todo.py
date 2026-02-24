"""Hamilton DAG for the todo audit."""

import ibis

from iacs.registry import Registry


def todo_table(registry: Registry) -> ibis.expr.types.Table | None:
    """Get the todo component table, or None if no todos exist."""
    if "todo" not in registry.component_types:
        return None
    table = registry.view("todo")
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
