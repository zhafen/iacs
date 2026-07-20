"""Tests for the Registrar base class."""

from pathlib import Path

import pytest
import pandas as pd
import ibis

from tests.conftest import make_registry
from tests.test_dataflows.dags import dataflow, dataflow_b
from iacs.registrar import Registrar


def _sample_registry():
    return make_registry(
        {
            "description": [
                {"entity_id": "e1", "value": "First entity"},
                {"entity_id": "e2", "value": "Second entity"},
            ]
        }
    )


def _registrar_with_test_dataflow():
    """Return a Registrar with the test dataflow module loaded directly."""
    a = Registrar(_sample_registry())
    a._dataflows = [dataflow]
    return a


class TestRegistrarConstruction:
    def test_can_create_with_registry(self):
        registry = _sample_registry()
        a = Registrar(registry)
        assert a is not None

    def test_registry_property(self):
        registry = _sample_registry()
        a = Registrar(registry)
        assert a.registry is registry


class TestRegistrarExecute:
    def test_execute_returns_dict(self):
        a = _registrar_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert isinstance(result, dict)

    def test_execute_result_contains_requested_keys(self):
        a = _registrar_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert "entity_summary" in result

    def test_execute_result_value_is_ibis_table(self):
        a = _registrar_with_test_dataflow()
        result = a.execute(["entity_summary"])
        assert isinstance(result["entity_summary"], ibis.expr.types.Table)

    def test_execute_result_has_expected_data(self):
        a = _registrar_with_test_dataflow()
        result = a.execute(["entity_summary"])
        df = result["entity_summary"].execute()
        assert len(df) == 2
        assert "entity_id" in df.columns
        assert "description" in df.columns

    def test_execute_multiple_nodes(self):
        a = _registrar_with_test_dataflow()
        result = a.execute(["description_table", "entity_summary"])
        assert "description_table" in result
        assert "entity_summary" in result

    def test_execute_empty_list_returns_empty_dict(self):
        a = _registrar_with_test_dataflow()
        result = a.execute([])
        assert result == {}


class TestRegistrarOutputs:
    def test_outputs_lists_available_nodes(self):
        a = _registrar_with_test_dataflow()
        outputs = a.outputs
        assert "entity_summary" in outputs
        assert "description_table" in outputs

    def test_outputs_does_not_include_input_nodes(self):
        a = _registrar_with_test_dataflow()
        outputs = a.outputs
        assert "registry" not in outputs


class TestLoadDataflow:
    def test_load_top_level_dataflow(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("etl.export_manifest")
        assert any(m.__name__ == "iacs.dataflows.etl.export_manifest" for m in a._dataflows)

    def test_load_subpackage_dataflow(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.requirement_coverage")
        assert any(
            m.__name__ == "iacs.dataflows.audit.requirement_coverage"
            for m in a._dataflows
        )

    def test_load_dataflow_adds_outputs(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.traceability")
        assert "traceability" in a.outputs

    def test_load_multiple_dataflows(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.traceability")
        a.load_dataflow("audit.todo")
        assert "traceability" in a.outputs
        assert "todo" in a.outputs

    def test_load_unknown_dataflow_raises(self):
        a = Registrar(_sample_registry())
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
            Registrar.from_manifest("examples/example")

        assert "validated_registry" in executed_vars, (
            "derive_components was not executed during from_manifest"
        )


class TestRegistrarUX:
    """This class tests Registrar as we expect to use it."""

    def test_setup_and_inspect(self):

        a = Registrar.from_manifest("examples/example")
        a.view("entity_id")
        assert a.get("component_type") == a.registry.get("component_type")

    def test_export_manifest(self, tmp_path):
        """Sometimes we just want to load and export in yaml formatting."""
        input_dir = "examples/example"
        output_dir = str(tmp_path)

        # Export
        a = Registrar.from_manifest(input_dir)
        a.execute("etl.export_manifest", output_dir=output_dir)

        # Reload and check
        a2 = Registrar.from_manifest(output_dir)
        pd.testing.assert_allclose(
            a.view("component_type"),
            a2.view("component_type"),
        )


class TestSaveAndLoadDatabase:
    """Tests for exporting/loading a Registrar's registry via a database file."""

    def test_save_creates_file(self, tmp_path):
        a = Registrar(_sample_registry())
        db_path = tmp_path / "registry.duckdb"
        a.save(db_path)
        assert db_path.exists()

    def test_load_recovers_component_types(self, tmp_path):
        a = Registrar(_sample_registry())
        db_path = tmp_path / "registry.duckdb"
        a.save(db_path)

        a2 = Registrar.load(db_path)

        assert set(a2.registry.component_types) == set(a.registry.component_types)

    def test_load_recovers_data(self, tmp_path):
        a = Registrar(_sample_registry())
        db_path = tmp_path / "registry.duckdb"
        a.save(db_path)

        a2 = Registrar.load(db_path)

        pd.testing.assert_frame_equal(
            a2.registry.get("description").execute().sort_values("entity_id").reset_index(drop=True),
            a.registry.get("description").execute().sort_values("entity_id").reset_index(drop=True),
        )

    def test_save_then_from_manifest_roundtrip_via_example(self, tmp_path):
        """Saving a manifest-loaded registry and reloading should preserve data."""
        a = Registrar.from_manifest("examples/example")
        db_path = tmp_path / "registry.duckdb"
        a.save(db_path)

        a2 = Registrar.load(db_path)

        assert set(a2.registry.component_types) == set(a.registry.component_types)


class TestLoadManifestWithTime:
    """Tests for load_manifest's time-associated slowly changing dimension support."""

    _SCHEMA = (
        "status_reading:\n"
        "    data:\n"
        "        - description: A slowly changing status reading.\n"
        "        - field:\n"
        "              as_of:\n"
        "                  type: str\n"
        "                  time_dimension: true\n"
        "              status:\n"
        "                  type: str\n"
    )

    def _write(self, dir_path, filename, content):
        (dir_path / filename).write_text(content)

    def test_null_time_dimension_field_filled_with_load_time(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: open\n")

        a = Registrar()
        a.load_manifest(tmp_path, time="2024-01-01")

        df = a.registry.get("status_reading").execute()
        assert df.iloc[0]["as_of"] == "2024-01-01"

    def test_explicit_time_dimension_value_not_overwritten(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(
            tmp_path, "reading.yaml",
            "cat_status:\n- status_reading:\n    status: open\n    as_of: explicit-time\n",
        )

        a = Registrar()
        a.load_manifest(tmp_path, time="2024-01-01")

        df = a.registry.get("status_reading").execute()
        assert df.iloc[0]["as_of"] == "explicit-time"

    def test_no_time_given_leaves_field_null(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: open\n")

        a = Registrar()
        a.load_manifest(tmp_path)

        df = a.registry.get("status_reading").execute()
        assert pd.isna(df.iloc[0]["as_of"])

    def test_view_current_returns_latest_version_across_loads(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: open\n")

        a = Registrar()
        a.load_manifest(tmp_path, time="2024-01-01")

        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: closed\n")
        a.load_manifest(tmp_path, time="2024-06-01")

        df = a.view_current("status_reading").execute()
        assert len(df) == 1
        assert df.iloc[0]["status_reading.status"] == "closed"
        assert df.iloc[0]["status_reading.as_of"] == "2024-06-01"

    def test_view_still_shows_full_history(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: open\n")

        a = Registrar()
        a.load_manifest(tmp_path, time="2024-01-01")

        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: closed\n")
        a.load_manifest(tmp_path, time="2024-06-01")

        df = a.registry.get("status_reading").execute()
        assert len(df) == 2

    def test_from_manifest_accepts_time(self, tmp_path):
        self._write(tmp_path, "schema.yaml", self._SCHEMA)
        self._write(tmp_path, "reading.yaml", "cat_status:\n- status_reading:\n    status: open\n")

        a = Registrar.from_manifest(tmp_path, time="2024-01-01")

        df = a.registry.get("status_reading").execute()
        assert df.iloc[0]["as_of"] == "2024-01-01"


class TestLoadManifest:
    def test_load_each_yaml_matches_directory(self, tmp_path):
        """Loading YAML files one at a time should match loading the directory."""
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )
        (tmp_path / "solutions.yaml").write_text(
            "sol_a:\n- description: Solution A\n"
        )

        a_all = Registrar.from_manifest(str(tmp_path))

        a_inc = Registrar()
        for yaml_file in sorted(tmp_path.rglob("*.yaml")):
            a_inc.load_manifest(str(yaml_file))

        assert set(a_all.registry.component_types) == set(a_inc.registry.component_types)

        for comp_type in a_all.registry.component_types:
            df_all = a_all.registry.get(comp_type).execute()
            df_inc = a_inc.registry.get(comp_type).execute()
            sort_by = sorted(df_all.columns)
            pd.testing.assert_frame_equal(
                df_all.sort_values(sort_by, na_position="last").reset_index(drop=True),
                df_inc.reindex(columns=df_all.columns).sort_values(sort_by, na_position="last").reset_index(drop=True),
                check_dtype=False,
            )

    def test_accepts_path_object_directly(self, tmp_path):
        """load_manifest/from_manifest accept a Path without the caller converting to str."""
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )

        a = Registrar.from_manifest(tmp_path)
        assert "requirement" in a.registry.component_types

        a2 = Registrar()
        a2.load_manifest(tmp_path)
        assert "requirement" in a2.registry.component_types

    def test_accepts_list_of_mixed_str_and_path(self, tmp_path):
        """A list of manifest paths may mix str and Path entries."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )
        (sub / "solutions.yaml").write_text("sol_a:\n- description: Solution A\n")

        a = Registrar.from_manifest([str(tmp_path / "requirements.yaml"), sub])
        assert "requirement" in a.registry.component_types


class TestUpdate:
    """Tests for `update`, the general-purpose incremental-merge method."""

    def test_load_manifest_is_a_thin_wrapper_around_update(self, tmp_path):
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )
        r = Registrar()
        r.load_manifest(tmp_path)
        assert "requirement" in r.registry.component_types

    def test_update_accepts_yaml_strings_without_input_dirs(self):
        r = Registrar()
        r.update(yaml_strings={
            "req": "req_a:\n- description: Requirement A\n- requirement\n"
        })
        assert "requirement" in r.registry.component_types

    def test_update_merges_yaml_strings_into_existing_registry(self):
        """An SCD-style update: attach a new position to an entity already in the registry."""
        example_dir = Path("examples/game_data")
        r = Registrar.from_manifest(example_dir)

        eids = r.registry.get("entity_id")
        player_eid = (
            eids.filter(eids["alias"].contains("player")).execute().iloc[0]["value"]
        )

        input_yaml = f"""
        updated_player_position:
            - same_as:
                target_entity_id: {player_eid}
            - position:
                x: 5
                y: 5
                z: 5
        """
        r.update(
            input_dirs=[example_dir],
            yaml_strings={"scd_update": input_yaml},
            time=1,
        )

        positions = r.view_current("position")
        assert positions.count().execute() == 1
        assert list(
            positions.execute().iloc[0][["position.x", "position.y", "position.z"]]
        ) == [5, 5, 5]

    def test_same_as_by_path_targets_entity_from_a_prior_update(self):
        """same_as's path-based `value` can target an entity registered by an
        earlier, separate `update()` call, not just one in the same batch —
        the existing registry's entity_id table is passed into derive.
        """
        r = Registrar()
        r.update(yaml_strings={
            "req": "req_a:\n- description: Requirement A\n- requirement\n"
        })
        eids = r.registry.get("entity_id")
        req_eid = eids.filter(eids["alias"] == "req_a").execute().iloc[0]["value"]

        r.update(yaml_strings={
            "extra": (
                "req_a_update:\n"
                "    - same_as:\n"
                "        value: req_a\n"
                "    - todo: Double check requirement A\n"
            )
        })

        todos = r.view("todo").execute()
        new_todo = todos[todos["todo.value"] == "Double check requirement A"]
        assert len(new_todo) == 1
        assert new_todo.iloc[0]["entity_id"] == req_eid
        # No disconnected second entity was minted for req_a_update.
        assert eids.filter(eids["alias"] == "req_a_update").count().execute() == 0
        assert r.registry.get("requirement").count().execute() == 1


class TestExportManifestMethod:
    """Tests for the `export_manifest` convenience method."""

    def test_export_manifest_writes_to_output_dir(self, tmp_path):
        input_dir = "examples/example"
        output_dir = str(tmp_path)

        r = Registrar.from_manifest(input_dir)
        saved = r.export_manifest(output_dir)

        assert saved
        assert all(Path(p).exists() for p in saved)

    def test_export_manifest_refreshes_in_place_without_output_dir(self, tmp_path):
        (tmp_path / "requirements.yaml").write_text(
            "req_a:\n- description: Requirement A\n- requirement\n"
        )
        r = Registrar.from_manifest(tmp_path)

        saved = r.export_manifest()

        assert saved
        assert all(Path(p).exists() for p in saved)


class TestViewProxies:
    """Tests that Registrar exposes the same view helpers as Registry, without `.registry`."""

    @staticmethod
    def _registrar():
        return Registrar.from_manifest("examples/example")

    def test_view_df_matches_registry_view_df(self):
        r = self._registrar()
        pd.testing.assert_frame_equal(
            r.view_df("description"), r.registry.view_df("description")
        )

    def test_view_entity_matches_registry_view_entity(self):
        r = self._registrar()
        entity_id = r.registry.get("entity_id").execute().iloc[0]["value"]
        assert r.view_entity(entity_id) == r.registry.view_entity(entity_id)

    def test_view_entity_df_matches_registry_view_entity_df(self):
        r = self._registrar()
        entity_id = r.registry.get("entity_id").execute().iloc[0]["value"]
        assert (
            r.view_entity_df(entity_id).keys()
            == r.registry.view_entity_df(entity_id).keys()
        )
