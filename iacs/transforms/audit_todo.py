"""Hamilton DAG for the todo audit."""

import ibis

from iacs.audit_system import AuditResult
from iacs.registry import Registry


def todo_table(registry: Registry) -> ibis.expr.types.Table | None:
    """Get the todo component table, or None if no todos exist."""
    if "todo" not in registry.component_types:
        return None
    table = registry.view("todo")
    if table.count().execute() == 0:
        return None
    return table


def todo(todo_table: ibis.expr.types.Table | None) -> AuditResult:
    """Produce the todo audit result."""
    if todo_table is None:
        return AuditResult(passed=True)

    results_df = todo_table.select("entity_id").distinct().execute()

    if "value" in todo_table.columns:
        msg_df = todo_table.select("entity_id", "value").execute()
    else:
        msg_df = todo_table.select("entity_id").execute()
        msg_df["value"] = ""

    messages = [
        f"{row['entity_id']}: {row['value']}" for _, row in msg_df.iterrows()
    ]

    return AuditResult(passed=False, messages=messages, results=results_df)
