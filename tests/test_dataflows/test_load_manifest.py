"""Tests for the load_manifest Hamilton DAG functions."""

import ibis
import pandas as pd
import pytest

import iacs.dataflows.load_manifest as load_manifest
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

    def _all_entities(self, result: dict) -> dict:
        """Flatten all per-file entity dicts into one dict (for assertions)."""
        merged = {}
        for entities in result.values():
            if isinstance(entities, dict):
                merged.update(entities)
        return merged

    def test_loads_single_yaml_file(self, minimal_yaml_dir):
        result = load_manifest.raw_entity_first_data([minimal_yaml_dir])
        assert isinstance(result, dict)
        assert "my_task" in self._all_entities(result)

    def test_loads_multiple_yaml_files(self, multi_file_yaml_dir):
        result = load_manifest.raw_entity_first_data([multi_file_yaml_dir])
        entities = self._all_entities(result)
        assert "my_task" in entities
        assert "my_infra" in entities

    def test_loads_yaml_from_subdirectories(self, multi_file_yaml_dir):
        result = load_manifest.raw_entity_first_data([multi_file_yaml_dir])
        # my_infra is in a subdirectory
        assert "my_infra" in self._all_entities(result)

    def test_empty_dir_has_only_builtin(self, tmp_path):
        result = load_manifest.raw_entity_first_data([str(tmp_path)])
        assert "builtins.components" in result
        assert len(result) == 1

    def test_always_includes_builtin(self, minimal_yaml_dir):
        result = load_manifest.raw_entity_first_data([minimal_yaml_dir])
        assert "builtins.components" in result

    def test_preserves_raw_structure(self, minimal_yaml_dir):
        result = load_manifest.raw_entity_first_data([minimal_yaml_dir])
        entities = self._all_entities(result)
        # The value should be the raw list from the YAML
        assert isinstance(entities["my_task"], list)
        assert {"description": "A task I need to complete."} in entities["my_task"]

    def test_keyed_by_file_path(self, minimal_yaml_dir):
        result = load_manifest.raw_entity_first_data([minimal_yaml_dir])
        # At least one key should end with 'minimal.yaml' (the user file)
        user_keys = [k for k in result if k != "builtins.components"]
        assert any(k.endswith("minimal.yaml") for k in user_keys)

    def test_accepts_single_file_path(self, tmp_path):
        yaml_file = tmp_path / "single.yaml"
        yaml_file.write_text("my_entity:\n- description: A thing.\n")
        result = load_manifest.raw_entity_first_data([str(yaml_file)])
        assert "my_entity" in self._all_entities(result)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_returns_registry_instance(self):
        spine = ibis.memtable(pd.DataFrame([{"entity_id": 1}]))
        comps = {"description": ibis.memtable(pd.DataFrame([{"entity_id": "e1", "value": "Hello"}]))}
        result = load_manifest.registry(spine, comps)
        assert isinstance(result, Registry)

    def test_registry_has_component_types(self):
        spine = ibis.memtable(pd.DataFrame([{"entity_id": 1}]))
        comps = {
            "description": ibis.memtable(pd.DataFrame([{"entity_id": "e1", "value": "Hello"}])),
            "task": ibis.memtable(pd.DataFrame([{"entity_id": "e1"}])),
        }
        result = load_manifest.registry(spine, comps)
        assert "description" in result.component_types
        assert "task" in result.component_types


# ---------------------------------------------------------------------------
# pathvalue_pairs
# ---------------------------------------------------------------------------

_FILE_ID = "test.yaml"


def _wrap(entities: dict) -> dict:
    """Wrap a flat entities dict in the file-keyed format expected by pathvalue_pairs."""
    return {_FILE_ID: entities}


def _path(entity_path: str) -> str:
    """Build the expected path string with the test file prefix."""
    return f"{_FILE_ID}:{entity_path}"


class TestPathvaluePairs:

    def test_returns_ibis_table(self):
        data = _wrap({"my_task": [{"description": "A task."}]})
        result = load_manifest.pathvalue_pairs(data)
        assert isinstance(result, ibis.Table)

    def test_has_path_and_value_columns(self):
        data = _wrap({"my_task": [{"description": "A task."}]})
        result = load_manifest.pathvalue_pairs(data)
        assert "path" in result.columns
        assert "value" in result.columns

    def test_scalar_component(self):
        """A dict component with a string value produces one (path, value) row."""
        data = _wrap({"my_task": [{"description": "A task."}]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        expected_path = _path("my_task[0].description")
        assert expected_path in df["path"].values
        row = df[df["path"] == expected_path]
        assert row["value"].iloc[0] == "A task."

    def test_tag_component(self):
        """A bare-string tag produces a row with an empty value."""
        data = _wrap({"my_task": ["task"]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        expected_path = _path("my_task[0].task")
        assert expected_path in df["path"].values
        assert df[df["path"] == expected_path]["value"].iloc[0] == ""

    def test_tag_index_preserved(self):
        """A tag at list index N shifts subsequent components to N+1."""
        data = _wrap({"my_task": ["task", {"description": "A task."}]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        assert _path("my_task[1].description") in df["path"].values

    def test_dict_valued_component(self):
        """A component whose value is a dict produces one row per sub-field."""
        data = _wrap({"entity": [{"requirement": {"priority": 1}}]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        expected_path = _path("entity[0].requirement.priority")
        assert expected_path in df["path"].values
        assert df[df["path"] == expected_path]["value"].iloc[0] == "1"

    def test_component_key_with_space(self):
        """Component keys containing spaces (e.g. 'solution of') are preserved."""
        data = _wrap({"entity": [{"solution of": "other_entity"}]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        expected_path = _path("entity[0].solution of")
        assert expected_path in df["path"].values
        assert df[df["path"] == expected_path]["value"].iloc[0] == "other_entity"

    def test_nested_entity_data_prefix(self):
        """Components of a nested entity are placed under the .data[N] prefix."""
        data = _wrap({"parent": {"data": [{"description": "A parent."}]}})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        assert _path("parent.data[0].description") in df["path"].values

    def test_nested_entity_sub_entities_recurse(self):
        """Sub-entities of a nested entity get their own paths."""
        data = _wrap({
            "parent": {
                "data": [{"description": "A parent."}],
                "child": [{"description": "A child."}],
            }
        })
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        assert _path("parent.data[0].description") in df["path"].values
        assert _path("parent.child[0].description") in df["path"].values

    def test_multiple_entities(self):
        """Multiple top-level entities each contribute their own paths."""
        data = _wrap({
            "req": [{"description": "A req."}],
            "infra": [{"description": "Infrastructure."}],
        })
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        assert _path("req[0].description") in df["path"].values
        assert _path("infra[0].description") in df["path"].values

    def test_multiple_files_produce_prefixed_paths(self):
        """Each file's paths are prefixed with that file's identifier."""
        data = {
            "file_a.yaml": {"entity_a": [{"description": "A."}]},
            "file_b.yaml": {"entity_b": [{"description": "B."}]},
        }
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        assert "file_a.yaml:entity_a[0].description" in df["path"].values
        assert "file_b.yaml:entity_b[0].description" in df["path"].values


# ---------------------------------------------------------------------------
# spine
# ---------------------------------------------------------------------------

def _pvp(pairs: list[tuple[str, str]]) -> ibis.Table:
    """Create a pathvalue_pairs ibis Table from (path, value) tuples."""
    return ibis.memtable(pd.DataFrame(pairs, columns=["path", "value"]))


class TestSpine:

    def _call(self, pairs):
        return load_manifest.spine(_pvp(pairs))

    def test_returns_ibis_table(self):
        result = self._call([("my_task[0].description", "A task.")])
        assert isinstance(result, ibis.Table)

    def test_has_required_columns(self):
        result = self._call([("my_task[0].description", "A task.")])
        for col in [
            "entity_id", "component_index", "entity_key",
            "component_type", "modifier", "filepath", "path",
        ]:
            assert col in result.columns

    def test_flat_entity_spine_row(self):
        """Flat entity path produces correct spine row."""
        spine = self._call([("my_task[0].description", "A task.")])
        df = spine.to_pandas()
        row = df[df["path"] == "my_task[0].description"].iloc[0]
        assert row["entity_id"] == dhash("my_task")
        assert row["component_index"] == 0
        assert row["entity_key"] == "my_task"
        assert row["component_type"] == "description"
        assert row["modifier"] is None or pd.isna(row["modifier"])

    def test_tag_component(self):
        """Bare-string tag produces a spine row with the tag name as component_type."""
        spine = self._call([("my_task[0].requirement", "")])
        df = spine.to_pandas()
        assert "my_task[0].requirement" in df["path"].values
        row = df[df["path"] == "my_task[0].requirement"].iloc[0]
        assert row["component_type"] == "requirement"

    def test_modifier_extracted(self):
        """'solution of' produces component_type='solution', modifier='of'."""
        spine = self._call([("entity[0].solution of", "other")])
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
        spine = self._call(pairs)
        df = spine.to_pandas()
        field_rows = df[df["component_type"] == "field"]
        assert len(field_rows) == 1
        assert field_rows.iloc[0]["path"] == "cat[0].field"

    def test_entity_key_is_last_path_segment(self):
        """entity_key is the last dot-separated segment of the entity path."""
        spine = self._call([("outer.inner[0].description", "Hi.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["entity_key"] == "inner"
        assert row["entity_id"] == dhash("outer.inner")

    def test_nested_entity_strips_data_suffix(self):
        """entity.data[N].key → entity_path='entity', entity_key='entity'."""
        spine = self._call([("parent.data[0].description", "A parent.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["entity_id"] == dhash("parent")
        assert row["entity_key"] == "parent"

    def test_file_prefixed_path(self):
        """File-prefixed paths produce entity_ids that include the file prefix."""
        spine = self._call([("file.yaml:my_entity[0].description", "Hi.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["entity_id"] == dhash("file.yaml:my_entity")
        assert row["entity_key"] == "my_entity"
        assert row["filepath"] == "file.yaml"

    def test_filepath_null_without_prefix(self):
        """Paths without a file prefix produce a NULL filepath."""
        spine = self._call([("my_entity[0].description", "Hi.")])
        df = spine.to_pandas()
        row = df.iloc[0]
        assert row["filepath"] is None or pd.isna(row["filepath"])


# ---------------------------------------------------------------------------
# component_tables
# ---------------------------------------------------------------------------

class TestComponentTables:

    def _call(self, data: dict) -> dict:
        wrapped = {_FILE_ID: data}
        pvp = load_manifest.pathvalue_pairs(wrapped)
        sp = load_manifest.spine(pvp)
        return load_manifest.component_tables(pvp, sp)

    def _eid(self, entity_key: str) -> str:
        return dhash(f"{_FILE_ID}:{entity_key}")

    def test_returns_dict_of_ibis_tables(self):
        data = {"entity": [{"description": "A thing."}]}
        result = self._call(data)
        assert isinstance(result, dict)
        for val in result.values():
            assert isinstance(val, ibis.Table)

    def test_keys_are_component_types(self):
        data = {
            "entity": [{"description": "A thing."}, "requirement"],
        }
        result = self._call(data)
        assert "description" in result
        assert "requirement" in result

    def test_scalar_component_has_value_column(self):
        """A simple key-value component produces a 'value' column."""
        data = {"entity": [{"description": "A thing."}]}
        result = self._call(data)
        df = result["description"].to_pandas()
        assert "value" in df.columns
        row = df[df["entity_id"] == self._eid("entity")].iloc[0]
        assert row["value"] == "A thing."

    def test_tag_component_has_value_column(self):
        """A bare-string tag produces a 'value' column with empty string."""
        data = {"entity": ["requirement"]}
        result = self._call(data)
        df = result["requirement"].to_pandas()
        assert "value" in df.columns
        row = df[df["entity_id"] == self._eid("entity")].iloc[0]
        assert row["value"] == ""

    def test_sub_field_component_has_field_columns(self):
        """A dict-valued component produces one column per sub-field."""
        data = {"entity": [{"field": {"name": "x", "type": "str"}}]}
        result = self._call(data)
        df = result["field"].to_pandas()
        assert "name" in df.columns
        assert "type" in df.columns
        row = df[df["entity_id"] == self._eid("entity")].iloc[0]
        assert row["name"] == "x"
        assert row["type"] == "str"

    def test_multi_field_component_collapsed_to_one_row(self):
        """Multiple sub-fields of the same component instance → one row."""
        data = {"cat": [{"field": {"name": "breed", "value": "orange", "type": "str"}}]}
        result = self._call(data)
        df = result["field"].to_pandas()
        assert len(df[df["entity_id"] == self._eid("cat")]) == 1

    def test_modifier_preserved(self):
        """Modifier from spine is carried into the component table."""
        data = {"entity": [{"solution of": "other"}]}
        result = self._call(data)
        df = result["solution"].to_pandas()
        row = df[df["entity_id"] == self._eid("entity")].iloc[0]
        assert row["modifier"] == "of"

    def test_entity_id_and_component_index_present(self):
        """Every component table has entity_id and component_index columns."""
        data = {"entity": [{"description": "A thing."}]}
        result = self._call(data)
        df = result["description"].to_pandas()
        assert "entity_id" in df.columns
        assert "component_index" in df.columns
