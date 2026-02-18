"""Minimal test: define and execute a Hamilton DAG over iacs registry data."""

from pathlib import Path

import ibis
from hamilton import driver, base

from iacs.transforms.manifest_to_registry import (
    raw_entity_first_data,
    flattened_entity_first_data,
    component_first_data,
    complete_schema,
    data_models,
    components_database,
    validated_components,
    registry,
)

import tests.test_transforms.test_transform_dataflow as dataflow_module

COMPONENTS_YAML = Path(__file__).parent.parent.parent / "components"


def test_hamilton_dag():
    raw = raw_entity_first_data(str(COMPONENTS_YAML))
    flat_result = flattened_entity_first_data(raw)
    flattened_data = flat_result["flattened_data"]
    name_to_id = flat_result["name_to_id"]
    comp_first = component_first_data(flattened_data, name_to_id)
    schema = complete_schema(comp_first["schema"], comp_first["parent"])
    models = data_models(schema)
    conn, comps = components_database(comp_first, models)
    v_comps = validated_components(comps, models)
    reg = registry(conn, v_comps)

    dr = driver.Driver(
        {"registry": reg},
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
