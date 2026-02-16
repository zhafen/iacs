"""Minimal test: define and execute a Hamilton DAG over iacs registry data."""

from pathlib import Path

import ibis
from hamilton import driver, base

from iacs.io_system import IOSystem
from iacs.registry import Registry

import tests.test_transform_dataflow as dataflow_module

COMPONENTS_YAML = Path(__file__).parent.parent / "components" / "components.yaml"


def test_hamilton_dag():
    io = IOSystem()
    entity_centered = io.read_entity_centered_file(str(COMPONENTS_YAML))
    registry = Registry.from_entity_centered(entity_centered)

    dr = driver.Driver(
        {"registry": registry},
        dataflow_module,
        adapter=base.DictResult(),
    )

    result = dr.execute(["entity_summary"])
    table = result["entity_summary"]

    assert isinstance(table, ibis.Table)
    df = table.to_pandas()
    assert len(df) > 0
    assert "entity_id" in df.columns
    assert "description" in df.columns
