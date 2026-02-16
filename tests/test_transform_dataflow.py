"""Hamilton dataflow module: functions here define the DAG nodes."""

import ibis

from iacs.registry import Registry


def id_table(registry: Registry) -> ibis.Table:
    return registry.table("id")


def description_table(registry: Registry) -> ibis.Table:
    return registry.table("description")


def entity_summary(id_table: ibis.Table, description_table: ibis.Table) -> ibis.Table:
    """Join id and description to get readable entity summaries."""
    return id_table.join(
        description_table, "entity_id"
    ).select("entity_id", "path", "key", description="value_right")
