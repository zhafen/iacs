"""Tests for the manifest_to_registry Hamilton DAG functions."""

import os
import tempfile
from pathlib import Path

import ibis
import pandas as pd
import pytest

import iacs.transforms.manifest_to_registry as manifest_to_registry
from iacs.registry import Registry
from iacs.utils import dhash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_yaml_dir(tmp_path):
    """Create a temp directory with a minimal YAML manifest."""
    (tmp_path / "minimal.yaml").write_text(
        "my_task:\n"
        "- description: A task I need to complete.\n"
        "- task\n"
    )
    return str(tmp_path)


@pytest.fixture
def multi_file_yaml_dir(tmp_path):
    """Create a temp directory with multiple YAML files including a subdirectory."""
    (tmp_path / "tasks.yaml").write_text(
        "my_task:\n"
        "- description: A task.\n"
        "- task\n"
    )
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "infra.yaml").write_text(
        "my_infra:\n"
        "- description: Infrastructure.\n"
        "- solution of: my_task\n"
    )
    return str(tmp_path)


# ---------------------------------------------------------------------------
# raw_entity_first_data
# ---------------------------------------------------------------------------

class TestRawEntityFirstData:

    def test_loads_single_yaml_file(self, minimal_yaml_dir):
        result = manifest_to_registry.raw_entity_first_data(minimal_yaml_dir)
        assert isinstance(result, dict)
        assert "my_task" in result

    def test_loads_multiple_yaml_files(self, multi_file_yaml_dir):
        result = manifest_to_registry.raw_entity_first_data(multi_file_yaml_dir)
        assert isinstance(result, dict)
        assert "my_task" in result
        assert "my_infra" in result

    def test_loads_yaml_from_subdirectories(self, multi_file_yaml_dir):
        result = manifest_to_registry.raw_entity_first_data(multi_file_yaml_dir)
        # my_infra is in a subdirectory
        assert "my_infra" in result

    def test_returns_empty_dict_for_empty_dir(self, tmp_path):
        result = manifest_to_registry.raw_entity_first_data(str(tmp_path))
        assert result == {}

    def test_preserves_raw_structure(self, minimal_yaml_dir):
        result = manifest_to_registry.raw_entity_first_data(minimal_yaml_dir)
        # The value should be the raw list from the YAML
        assert isinstance(result["my_task"], list)
        assert {"description": "A task I need to complete."} in result["my_task"]


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_returns_registry_instance(self):
        con = ibis.duckdb.connect()
        con.create_table("description", {"entity_id": ["e1"], "value": ["Hello"]})
        spine = ibis.memtable(pd.DataFrame([{"entity_id": 1}]))
        comps = {"description": con.table("description")}
        result = manifest_to_registry.registry(con, spine, comps)
        assert isinstance(result, Registry)

    def test_registry_has_component_types(self):
        con = ibis.duckdb.connect()
        con.create_table("description", {"entity_id": ["e1"], "value": ["Hello"]})
        con.create_table("task", {"entity_id": ["e1"]})
        spine = ibis.memtable(pd.DataFrame([{"entity_id": 1}]))
        comps = {
            "description": con.table("description"),
            "task": con.table("task"),
        }
        result = manifest_to_registry.registry(con, spine, comps)
        assert "description" in result.component_types
        assert "task" in result.component_types


# ---------------------------------------------------------------------------
# pathvalue_pairs
# ---------------------------------------------------------------------------

class TestPathvaluePairs:

    @pytest.fixture
    def conn(self):
        return manifest_to_registry.db_conn()

    def test_returns_ibis_table(self, conn):
        data = {"my_task": [{"description": "A task."}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        assert isinstance(result, ibis.Table)

    def test_has_path_and_value_columns(self, conn):
        data = {"my_task": [{"description": "A task."}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        assert "path" in result.columns
        assert "value" in result.columns

    def test_scalar_component(self, conn):
        """A dict component with a string value produces one (path, value) row."""
        data = {"my_task": [{"description": "A task."}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "my_task[0].description" in df["path"].values
        row = df[df["path"] == "my_task[0].description"]
        assert row["value"].iloc[0] == "A task."

    def test_tag_component(self, conn):
        """A bare-string tag produces a row with an empty value."""
        data = {"my_task": ["task"]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "my_task[0].task" in df["path"].values
        assert df[df["path"] == "my_task[0].task"]["value"].iloc[0] == ""

    def test_tag_index_preserved(self, conn):
        """A tag at list index N shifts subsequent components to N+1."""
        data = {"my_task": ["task", {"description": "A task."}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "my_task[1].description" in df["path"].values

    def test_dict_valued_component(self, conn):
        """A component whose value is a dict produces one row per sub-field."""
        data = {"entity": [{"requirement": {"priority": 1}}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "entity[0].requirement.priority" in df["path"].values
        assert df[df["path"] == "entity[0].requirement.priority"]["value"].iloc[0] == "1"

    def test_component_key_with_space(self, conn):
        """Component keys containing spaces (e.g. 'solution of') are preserved."""
        data = {"entity": [{"solution of": "other_entity"}]}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "entity[0].solution of" in df["path"].values
        assert df[df["path"] == "entity[0].solution of"]["value"].iloc[0] == "other_entity"

    def test_nested_entity_data_prefix(self, conn):
        """Components of a nested entity are placed under the .data[N] prefix."""
        data = {"parent": {"data": [{"description": "A parent."}]}}
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "parent.data[0].description" in df["path"].values

    def test_nested_entity_sub_entities_recurse(self, conn):
        """Sub-entities of a nested entity get their own paths."""
        data = {
            "parent": {
                "data": [{"description": "A parent."}],
                "child": [{"description": "A child."}],
            }
        }
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "parent.data[0].description" in df["path"].values
        assert "parent.child[0].description" in df["path"].values

    def test_multiple_entities(self, conn):
        """Multiple top-level entities each contribute their own paths."""
        data = {
            "req": [{"description": "A req."}],
            "infra": [{"description": "Infrastructure."}],
        }
        result = manifest_to_registry.pathvalue_pairs(data, conn)
        df = result.to_pandas()
        assert "req[0].description" in df["path"].values
        assert "infra[0].description" in df["path"].values


# ---------------------------------------------------------------------------
# parsed_paths
# ---------------------------------------------------------------------------

def _pvp(pairs: list[tuple[str, str]]) -> ibis.Table:
    """Create a pathvalue_pairs ibis Table from (path, value) tuples."""
    return ibis.memtable(pd.DataFrame(pairs, columns=["path", "value"]))


class TestParsedPaths:

    def _call(self, pairs):
        pvp = _pvp(pairs)
        return manifest_to_registry.parsed_paths(pvp)

    def test_returns_two_ibis_tables(self):
        spine, hierarchy = self._call([("my_task[0].description", "A task.")])
        assert isinstance(spine, ibis.Table)
        assert isinstance(hierarchy, ibis.Table)

    def test_spine_has_required_columns(self):
        spine, _ = self._call([("my_task[0].description", "A task.")])
        for col in ["entity_id", "component_index", "entity_key", "component_type", "modifier", "path"]:
            assert col in spine.columns

    def test_hierarchy_has_required_columns(self):
        _, hierarchy = self._call([
            ("parent.data[0].description", "A parent."),
            ("parent.child[0].description", "A child."),
        ])
        assert "entity_id" in hierarchy.columns
        assert "parent_id" in hierarchy.columns

    def test_flat_entity_spine_row(self):
        """Flat entity path produces correct spine row."""
        spine, _ = self._call([("my_task[0].description", "A task.")])
        df = spine.to_pandas()
        row = df[df["path"] == "my_task[0].description"].iloc[0]
        assert row["entity_id"] == dhash("my_task")
        assert row["component_index"] == 0
        assert row["entity_key"] == "my_task"
        assert row["component_type"] == "description"
        assert row["modifier"] is None or pd.isna(row["modifier"])

    def test_tag_component(self):
        """Bare-string tag produces a spine row with the tag name as component_type."""
        spine, _ = self._call([("my_task[0].requirement", "")])
        df = spine.to_pandas()
        assert "my_task[0].requirement" in df["path"].values
        row = df[df["path"] == "my_task[0].requirement"].iloc[0]
        assert row["component_type"] == "requirement"

    def test_modifier_extracted(self):
        """'solution of' produces component_type='solution', modifier='of'."""
        spine, _ = self._call([("entity[0].solution of", "other")])
        df = spine.to_pandas()
        row = df[df["path"] == "entity[0].solution of"].iloc[0]
        assert row["component_type"] == "solution"
        assert row["modifier"] == "of"

    def test_deduplication_multi_field(self):
        """Multiple paths with the same entity/index/type produce one spine row."""
        pairs = [
            ("cat[0].field.name", "whiskers"),
            ("cat[0].field.value", "The cat's name."),
            ("cat[0].field.type", "str"),
        ]
        spine, _ = self._call(pairs)
        df = spine.to_pandas()
        field_rows = df[df["component_type"] == "field"]
        assert len(field_rows) == 1
        assert field_rows.iloc[0]["path"] == "cat[0].field"

    def test_entity_key_is_last_path_segment(self):
        """entity_key is the last dot-separated segment of the entity path."""
        spine, _ = self._call([("outer.inner[0].description", "Hi.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["entity_key"] == "inner"
        assert row["entity_id"] == dhash("outer.inner")

    def test_nested_entity_strips_data_suffix(self):
        """entity.data[N].key → entity_path='entity', entity_key='entity'."""
        spine, _ = self._call([("parent.data[0].description", "A parent.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["entity_id"] == dhash("parent")
        assert row["entity_key"] == "parent"

    def test_hierarchy_parent_child(self):
        """A sub-entity whose parent exists in the data produces a hierarchy row."""
        pairs = [
            ("parent.data[0].description", "A parent."),
            ("parent.child[0].description", "A child."),
        ]
        _, hierarchy = self._call(pairs)
        df = hierarchy.to_pandas()
        assert len(df) >= 1
        child_row = df[df["entity_id"] == dhash("parent.child")]
        assert len(child_row) == 1
        assert child_row.iloc[0]["parent_id"] == dhash("parent")

    def test_empty_hierarchy_for_flat_entities(self):
        """Flat top-level entities with no nesting produce an empty hierarchy."""
        pairs = [
            ("task[0].description", "A task."),
            ("infra[0].description", "Infrastructure."),
        ]
        _, hierarchy = self._call(pairs)
        df = hierarchy.to_pandas()
        assert len(df) == 0
