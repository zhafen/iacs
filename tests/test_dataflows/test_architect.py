"""Tests for the Architect base class."""

import ibis

from tests.conftest import make_registry
from tests.test_dataflows.dags import dataflow, dataflow_b
from iacs.architect import Architect


def _sample_registry():
    return make_registry(
        {
            "description": [
                {"entity_id": "e1", "value": "First entity"},
                {"entity_id": "e2", "value": "Second entity"},
            ]
        }
    )


class TestArchitectConstruction:
    def test_can_create_with_registry_and_dataflows(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        assert ts is not None

    def test_accepts_multiple_dataflow_modules(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow, dataflow_b])
        assert ts is not None


class TestArchitectExecute:
    def test_execute_returns_dict(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute(["entity_summary"])
        assert isinstance(result, dict)

    def test_execute_result_contains_requested_keys(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute(["entity_summary"])
        assert "entity_summary" in result

    def test_execute_result_value_is_ibis_table(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute(["entity_summary"])
        assert isinstance(result["entity_summary"], ibis.expr.types.Table)

    def test_execute_result_has_expected_data(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute(["entity_summary"])
        df = result["entity_summary"].execute()
        assert len(df) == 2
        assert "entity_id" in df.columns
        assert "description" in df.columns

    def test_execute_multiple_nodes(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute(["description_table", "entity_summary"])
        assert "description_table" in result
        assert "entity_summary" in result

    def test_execute_empty_list_returns_empty_dict(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        result = ts.execute([])
        assert result == {}


class TestArchitectOutputs:
    def test_outputs_lists_available_nodes(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        outputs = ts.outputs
        assert "entity_summary" in outputs
        assert "description_table" in outputs

    def test_outputs_does_not_include_input_nodes(self):
        registry = _sample_registry()
        ts = Architect(registry, [dataflow])
        outputs = ts.outputs
        assert "registry" not in outputs
