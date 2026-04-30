"""Tests for the Architect base class."""

import pytest
import pandas as pd
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


class TestFromManifestRunsDeriveComponents:
    def test_derive_components_runs_on_from_manifest(self):
        """derive_components should run automatically during from_manifest."""
        from unittest.mock import patch
        from hamilton import driver as hamilton_driver

        executed_vars = []
        original_execute = hamilton_driver.Driver.execute

        def capture_execute(self, final_vars, **kwargs):
            executed_vars.extend(final_vars)
            return original_execute(self, final_vars, **kwargs)

        with patch.object(hamilton_driver.Driver, "execute", capture_execute):
            Architect.from_manifest("examples/example")

        assert "derived_registry" in executed_vars, (
            "derive_components.derived_registry was not executed during from_manifest"
        )


class TestArchitectUX:
    """This class tests Architect as we expect to use it."""

    def test_setup_and_inspect(self):

        a = Architect.from_manifest("examples/example")
        a.view("entity_id")
        assert a.get("component_type") == a.registry.get("component_type")

    def test_export_manifest(self, tmp_path):
        """Sometimes we just want to load and export in yaml formatting."""
        input_dir = "examples/example"
        output_dir = str(tmp_path)

        # Export
        a = Architect.from_manifest(input_dir)
        a.execute("export_manifest", output_dir=output_dir)

        # Reload and check
        a2 = Architect.from_manifest(output_dir)
        pd.testing.assert_allclose(
            a.view("component_type"),
            a2.view("component_type"),
        )


class TestLoadManifest:
    def test_load_each_yaml_matches_directory(self, tmp_path):
        """Loading YAML files one at a time should match loading the directory."""
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )
        (tmp_path / "solutions.yaml").write_text(
            "sol_a:\n- description: Solution A\n"
        )

        a_all = Architect.from_manifest(str(tmp_path))

        a_inc = Architect()
        for yaml_file in sorted(tmp_path.rglob("*.yaml")):
            a_inc.load_manifest(str(yaml_file))

        assert set(a_all.registry.component_types) == set(a_inc.registry.component_types)

        for comp_type in a_all.registry.component_types:
            df_all = a_all.registry.get(comp_type).execute()
            df_inc = a_inc.registry.get(comp_type).execute()
            # "value" is the hash column in entity_id table; other tables use entity_id + component_index
            sort_by = [c for c in ["value", "entity_id", "component_index"] if c in df_all.columns]
            pd.testing.assert_frame_equal(
                df_all.sort_values(sort_by).reset_index(drop=True),
                df_inc.sort_values(sort_by).reset_index(drop=True),
                check_dtype=False,
            )
