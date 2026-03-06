"""Tests for the Architect base class."""

import pytest
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


def _architect_with_test_dataflow():
    """Return an Architect with the test dataflow module loaded directly."""
    a = Architect(_sample_registry())
    a._dataflows = [dataflow]
    a._rebuild_driver()
    return a


class TestArchitectConstruction:
    def test_can_create_with_registry(self):
        registry = _sample_registry()
        a = Architect(registry)
        assert a is not None

    def test_registry_property(self):
        registry = _sample_registry()
        a = Architect(registry)
        assert a.registry is registry


class TestArchitectExecute:
    def test_execute_returns_dict(self):
        a = _architect_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert isinstance(result, dict)

    def test_execute_result_contains_requested_keys(self):
        a = _architect_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert "entity_summary" in result

    def test_execute_result_value_is_ibis_table(self):
        a = _architect_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert isinstance(result["entity_summary"], ibis.expr.types.Table)

    def test_execute_result_has_expected_data(self):
        a = _architect_with_test_dataflow()
        result = a.execute(["entity_summary"])
        df = result["entity_summary"].execute()
        assert len(df) == 2
        assert "entity_id" in df.columns
        assert "description" in df.columns

    def test_execute_multiple_nodes(self):
        a = _architect_with_test_dataflow()
        result = a.execute(["description_table", "entity_summary"])
        assert "description_table" in result
        assert "entity_summary" in result

    def test_execute_empty_list_returns_empty_dict(self):
        a = _architect_with_test_dataflow()
        result = a.execute([])
        assert result == {}


class TestArchitectOutputs:
    def test_outputs_lists_available_nodes(self):
        a = _architect_with_test_dataflow()
        outputs = a.outputs
        assert "entity_summary" in outputs
        assert "description_table" in outputs

    def test_outputs_does_not_include_input_nodes(self):
        a = _architect_with_test_dataflow()
        outputs = a.outputs
        assert "registry" not in outputs


class TestLoadDataflow:
    def test_load_top_level_dataflow(self):
        a = Architect(_sample_registry())
        a.load_dataflow("export_manifest")
        assert any(m.__name__ == "iacs.dataflows.export_manifest" for m in a._dataflows)

    def test_load_subpackage_dataflow(self):
        a = Architect(_sample_registry())
        a.load_dataflow("audit.requirement_coverage")
        assert any(
            m.__name__ == "iacs.dataflows.audit.requirement_coverage"
            for m in a._dataflows
        )

    def test_load_dataflow_adds_outputs(self):
        a = Architect(_sample_registry())
        a.load_dataflow("audit.traceability")
        assert "traceability" in a.outputs

    def test_load_multiple_dataflows(self):
        a = Architect(_sample_registry())
        a.load_dataflow("audit.traceability")
        a.load_dataflow("audit.todo")
        assert "traceability" in a.outputs
        assert "todo" in a.outputs

    def test_load_unknown_dataflow_raises(self):
        a = Architect(_sample_registry())
        with pytest.raises(ValueError, match="nonexistent"):
            a.load_dataflow("nonexistent")
