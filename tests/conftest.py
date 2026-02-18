"""Shared test fixtures and helpers."""

import ibis
import pandas as pd

from iacs.registry import Registry


def make_registry(components: dict[str, list[dict]]) -> Registry:
    """Create a Registry from component-first data.

    Args:
        components: Dict mapping component type names to lists of row dicts.
            Each row dict should include "entity_id" plus any component fields.

    Returns:
        A Registry backed by a DuckDB connection.
    """
    conn = ibis.duckdb.connect()
    comp_tables = {}
    for comp_type, rows in components.items():
        df = pd.DataFrame(rows)
        conn.create_table(comp_type, df)
        comp_tables[comp_type] = conn.table(comp_type)
    return Registry(conn, comp_tables)
