"""Tests for the load_manifest Hamilton DAG functions."""

from pathlib import Path

import ibis
import pandas as pd
import pytest

import iacs.dataflows.etl.load_manifest as load_manifest
import iacs.dataflows.etl.load_yaml as load_yaml
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
        "- parent: task\n"
    )
    return str(tmp_path)


@pytest.fixture
def multi_file_yaml_dir(tmp_path):
    """Create a temp directory with multiple YAML files including a subdirectory."""
    (tmp_path / "tasks.yaml").write_text(
        "my_task:\n"
        "- description: A task.\n"
        "- parent: task\n"
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
    """Tests for load_yaml.raw_entity_first_data (YAML source loader)."""

    def _all_entities(self, result: dict) -> dict:
        """Flatten all per-file entity dicts into one dict (for assertions)."""
        merged = {}
        for entities in result.values():
            if isinstance(entities, dict):
                merged.update(entities)
        return merged

    def test_loads_single_yaml_file(self, minimal_yaml_dir):
        result = load_yaml.raw_entity_first_data([minimal_yaml_dir])
        assert isinstance(result, dict)
        assert "my_task" in self._all_entities(result)

    def test_loads_multiple_yaml_files(self, multi_file_yaml_dir):
        result = load_yaml.raw_entity_first_data([multi_file_yaml_dir])
        entities = self._all_entities(result)
        assert "my_task" in entities
        assert "my_infra" in entities

    def test_loads_yaml_from_subdirectories(self, multi_file_yaml_dir):
        result = load_yaml.raw_entity_first_data([multi_file_yaml_dir])
        assert "my_infra" in self._all_entities(result)

    def test_empty_dir_has_only_builtin(self, tmp_path):
        result = load_yaml.raw_entity_first_data([str(tmp_path)])
        assert "builtins.components" in result
        assert len(result) == 1

    def test_always_includes_builtin(self, minimal_yaml_dir):
        result = load_yaml.raw_entity_first_data([minimal_yaml_dir])
        assert "builtins.components" in result

    def test_preserves_raw_structure(self, minimal_yaml_dir):
        result = load_yaml.raw_entity_first_data([minimal_yaml_dir])
        entities = self._all_entities(result)
        assert isinstance(entities["my_task"], list)
        assert {"description": "A task I need to complete."} in entities["my_task"]

    def test_keyed_by_file_path(self, minimal_yaml_dir):
        result = load_yaml.raw_entity_first_data([minimal_yaml_dir])
        user_keys = [k for k in result if k != "builtins.components"]
        assert any(k.endswith("minimal.yaml") for k in user_keys)

    def test_accepts_single_file_path(self, tmp_path):
        yaml_file = tmp_path / "single.yaml"
        yaml_file.write_text("my_entity:\n- description: A thing.\n")
        result = load_yaml.raw_entity_first_data([str(yaml_file)])
        assert "my_entity" in self._all_entities(result)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def _make_entity_id_table():
    df = pd.DataFrame([{
        "value": "abc", "path": "test:e", "alias": "e",
        "entity_key": "e", "filepath": "test",
    }])
    return ibis.memtable(df)


def _make_component_type_table():
    df = pd.DataFrame([{
        "entity_id": "abc", "component_index": 0,
        "component_type": "description", "modifier": pd.NA,
    }])
    df["modifier"] = df["modifier"].astype(pd.StringDtype())
    return ibis.memtable(df)


def _make_empty_authored_parent():
    """Return an empty authored_parent table matching the expected schema."""
    empty_df = pd.DataFrame(columns=["entity_id", "component_index", "modifier", "value"])
    empty_df["entity_id"] = empty_df["entity_id"].astype(pd.StringDtype())
    empty_df["component_index"] = empty_df["component_index"].astype("int32")
    empty_df["modifier"] = empty_df["modifier"].astype(pd.StringDtype())
    empty_df["value"] = empty_df["value"].astype(pd.StringDtype())
    return ibis.memtable(empty_df)


class TestRegistry:

    def test_returns_registry_instance(self):
        eid = _make_entity_id_table()
        ct = _make_component_type_table()
        comps = {"description": ibis.memtable(pd.DataFrame([{"entity_id": "e1", "value": "Hello"}]))}
        ap = _make_empty_authored_parent()
        result = load_manifest.registry(eid, ct, comps, ap)
        assert isinstance(result, Registry)

    def test_registry_has_component_types(self):
        eid = _make_entity_id_table()
        ct = _make_component_type_table()
        comps = {
            "description": ibis.memtable(pd.DataFrame([{"entity_id": "e1", "value": "Hello"}])),
            "task": ibis.memtable(pd.DataFrame([{"entity_id": "e1"}])),
        }
        ap = _make_empty_authored_parent()
        result = load_manifest.registry(eid, ct, comps, ap)
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
        data = _wrap({"entity": [{"requirement": {"value": 1}}]})
        result = load_manifest.pathvalue_pairs(data)
        df = result.to_pandas()
        expected_path = _path("entity[0].requirement.value")
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
# entity_id_table and component_type_table
# ---------------------------------------------------------------------------

def _pvp(pairs: list[tuple[str, str]]) -> ibis.Table:
    """Create a pathvalue_pairs ibis Table from (path, value) tuples."""
    return ibis.memtable(pd.DataFrame(pairs, columns=["path", "value"]))


# ---------------------------------------------------------------------------
# component_tables
# ---------------------------------------------------------------------------

class TestComponentTables:

    def _call(self, data: dict) -> dict:
        wrapped = {_FILE_ID: data}
        pvp = load_manifest.pathvalue_pairs(wrapped)
        kvs = load_manifest.keyvalue_store(pvp)
        return load_manifest.component_tables(kvs)

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


# ---------------------------------------------------------------------------
# raw_csv_data
# ---------------------------------------------------------------------------

class TestRawCsvData:

    def test_loads_csv_from_directory(self, tmp_path):
        """CSV files in a directory are loaded and keyed by path identifier."""
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name,priority\nalpha,1\nbeta,2\n")
        result = load_manifest.raw_csv_data([str(tmp_path)])
        assert isinstance(result, dict)
        assert len(result) == 1
        file_id = next(iter(result))
        assert file_id.endswith("task.csv")
        df = result[file_id]
        assert list(df.columns) == ["name", "priority"]
        assert len(df) == 2

    def test_loads_explicit_csv_file(self, tmp_path):
        """A CSV file path passed directly is loaded."""
        csv_file = tmp_path / "req.csv"
        csv_file.write_text("id,text\n1,Requirement A\n")
        result = load_manifest.raw_csv_data([str(csv_file)])
        assert len(result) == 1
        df = next(iter(result.values()))
        assert "id" in df.columns

    def test_empty_directory_returns_empty_dict(self, tmp_path):
        """Directory with no CSV files returns an empty dict."""
        result = load_manifest.raw_csv_data([str(tmp_path)])
        assert result == {}

    def test_recursive_subdirectory(self, tmp_path):
        """CSV files in subdirectories are discovered recursively."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "infra.csv").write_text("host,port\nserver1,80\n")
        result = load_manifest.raw_csv_data([str(tmp_path)])
        assert len(result) == 1

    def test_ignores_yaml_files(self, tmp_path):
        """YAML files in the directory are not loaded by raw_csv_data."""
        (tmp_path / "task.yaml").write_text("my_task:\n- description: A task.\n")
        (tmp_path / "data.csv").write_text("col\nval\n")
        result = load_manifest.raw_csv_data([str(tmp_path)])
        assert len(result) == 1

    def test_returns_dataframes(self, tmp_path):
        """Values are pd.DataFrame instances."""
        (tmp_path / "comp.csv").write_text("x,y\n1,2\n")
        result = load_manifest.raw_csv_data([str(tmp_path)])
        for df in result.values():
            assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# csv_component_tables
# ---------------------------------------------------------------------------

class TestCsvComponentTables:

    def _make_raw(self, tmp_path, filename, content):
        f = tmp_path / filename
        f.write_text(content)
        return load_manifest.raw_csv_data([str(f)])

    def test_returns_dict_of_ibis_tables(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_component_tables(raw)
        assert isinstance(result, dict)
        for val in result.values():
            assert isinstance(val, ibis.Table)

    def test_stem_is_key(self, tmp_path):
        raw = self._make_raw(tmp_path, "requirement.csv", "text\nReq A\n")
        result = load_manifest.csv_component_tables(raw)
        assert "requirement" in result

    def test_entity_id_column_present(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_component_tables(raw)
        df = result["task"].to_pandas()
        assert "entity_id" in df.columns

    def test_entity_id_is_dhash(self, tmp_path):
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name\nalpha\n")
        file_id = str(csv_file.relative_to(Path.cwd())) if csv_file.is_relative_to(Path.cwd()) else str(csv_file)
        raw = load_manifest.raw_csv_data([str(csv_file)])
        result = load_manifest.csv_component_tables(raw)
        df = result["task"].to_pandas()
        actual_file_id = next(iter(raw.keys()))
        expected_id = dhash(actual_file_id + ":0")
        assert df.iloc[0]["entity_id"] == expected_id

    def test_component_index_is_zero(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\nbeta\n")
        result = load_manifest.csv_component_tables(raw)
        df = result["task"].to_pandas()
        assert (df["component_index"] == 0).all()

    def test_modifier_is_null(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_component_tables(raw)
        df = result["task"].to_pandas()
        assert df["modifier"].isna().all()

    def test_csv_columns_become_fields(self, tmp_path):
        raw = self._make_raw(tmp_path, "req.csv", "title,priority\nReq A,1\n")
        result = load_manifest.csv_component_tables(raw)
        df = result["req"].to_pandas()
        assert "title" in df.columns
        assert "priority" in df.columns

    def test_multiple_files_same_stem_unioned(self, tmp_path):
        f1 = tmp_path / "sub1"
        f1.mkdir()
        f2 = tmp_path / "sub2"
        f2.mkdir()
        (f1 / "task.csv").write_text("name\nalpha\n")
        (f2 / "task.csv").write_text("name\nbeta\n")
        raw = load_manifest.raw_csv_data([str(tmp_path)])
        result = load_manifest.csv_component_tables(raw)
        df = result["task"].to_pandas()
        assert len(df) == 2


# ---------------------------------------------------------------------------
# csv_spine
# ---------------------------------------------------------------------------

class TestCsvSpine:

    def _make_raw(self, tmp_path, filename, content):
        f = tmp_path / filename
        f.write_text(content)
        return load_manifest.raw_csv_data([str(f)])

    def test_returns_ibis_table(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_spine(raw)
        assert isinstance(result, ibis.Table)

    def test_has_required_columns(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_spine(raw)
        for col in ["entity_id", "component_index", "entity_key", "component_type",
                    "modifier", "filepath", "path"]:
            assert col in result.columns

    def test_one_row_per_csv_row(self, tmp_path):
        raw = self._make_raw(tmp_path, "req.csv", "text\nA\nB\nC\n")
        result = load_manifest.csv_spine(raw)
        assert len(result.to_pandas()) == 3

    def test_entity_id_uses_dhash(self, tmp_path):
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name\nalpha\n")
        raw = load_manifest.raw_csv_data([str(csv_file)])
        result = load_manifest.csv_spine(raw)
        df = result.to_pandas()
        file_id = next(iter(raw.keys()))
        expected_id = dhash(file_id + ":0")
        assert df.iloc[0]["entity_id"] == expected_id

    def test_entity_key_and_component_type_are_stem(self, tmp_path):
        raw = self._make_raw(tmp_path, "requirement.csv", "text\nReq A\n")
        result = load_manifest.csv_spine(raw)
        df = result.to_pandas()
        assert df.iloc[0]["entity_key"] == "requirement"
        assert df.iloc[0]["component_type"] == "requirement"

    def test_path_format(self, tmp_path):
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name\nalpha\n")
        raw = load_manifest.raw_csv_data([str(csv_file)])
        result = load_manifest.csv_spine(raw)
        df = result.to_pandas()
        file_id = next(iter(raw.keys()))
        expected_path = f"{file_id}:task[0].task"
        assert df.iloc[0]["path"] == expected_path

    def test_modifier_is_null(self, tmp_path):
        raw = self._make_raw(tmp_path, "task.csv", "name\nalpha\n")
        result = load_manifest.csv_spine(raw)
        df = result.to_pandas()
        assert df["modifier"].isna().all()

    def test_filepath_is_file_id(self, tmp_path):
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name\nalpha\n")
        raw = load_manifest.raw_csv_data([str(csv_file)])
        result = load_manifest.csv_spine(raw)
        df = result.to_pandas()
        file_id = next(iter(raw.keys()))
        assert df.iloc[0]["filepath"] == file_id


# ---------------------------------------------------------------------------
# component_tables union with csv_component_tables
# ---------------------------------------------------------------------------

class TestComponentTablesWithCsv:

    def test_csv_only_type_included(self, tmp_path):
        """CSV-only component types appear in the result."""
        csv_file = tmp_path / "task.csv"
        csv_file.write_text("name\nalpha\n")
        raw = load_manifest.raw_csv_data([str(csv_file)])
        csv_ct = load_manifest.csv_component_tables(raw)

        pairs = [("file.yaml:entity[0].description", "Hi.")]
        pvp = ibis.memtable(pd.DataFrame(pairs, columns=["path", "value"]))
        kvs = load_manifest.keyvalue_store(pvp)
        result = load_manifest.component_tables(kvs, csv_ct)
        assert "description" in result
        assert "task" in result

    def test_shared_type_rows_merged(self, tmp_path):
        """When both YAML and CSV have the same component type, rows are concatenated."""
        csv_file = tmp_path / "description.csv"
        csv_file.write_text("value\nCSV description\n")
        raw = load_manifest.raw_csv_data([str(csv_file)])
        csv_ct = load_manifest.csv_component_tables(raw)

        pairs = [("file.yaml:entity[0].description", "YAML description.")]
        pvp = ibis.memtable(pd.DataFrame(pairs, columns=["path", "value"]))
        kvs = load_manifest.keyvalue_store(pvp)
        result = load_manifest.component_tables(kvs, csv_ct)
        df = result["description"].to_pandas()
        assert len(df) == 2
