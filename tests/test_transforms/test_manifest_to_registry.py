"""Tests for the manifest_to_registry Hamilton DAG functions."""

import os
import tempfile
from pathlib import Path

import ibis
import pandas as pd
import pydantic
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


@pytest.fixture
def nested_entity_data():
    """Raw entity-first data with hierarchical nesting."""
    return {
        "core_task": {
            "data": [
                {"description": "The main task."},
                "task",
            ],
            "subtask_a": [
                {"description": "A subtask."},
                "task",
            ],
        },
    }


@pytest.fixture
def flat_entity_data():
    """Flattened entity-first data (no hierarchy, parent components added) with hashed IDs."""
    core_id = dhash("core_task")
    sub_id = dhash("core_task.subtask_a")
    return {
        core_id: [
            {"description": "The main task."},
            "task",
        ],
        sub_id: [
            {"description": "A subtask."},
            "task",
            {"parent": core_id},
        ],
    }


@pytest.fixture
def flat_entity_name_to_id():
    """Name-to-id mapping corresponding to flat_entity_data."""
    core_id = dhash("core_task")
    sub_id = dhash("core_task.subtask_a")
    return {
        "core_task": core_id,
        "subtask_a": sub_id,
        "core_task.subtask_a": sub_id,
    }


@pytest.fixture
def sample_component_first():
    """Component-first data with schema and parent components."""
    return {
        "description": [
            {"entity_id": "e1", "value": "A task."},
            {"entity_id": "e2", "value": "A subtask."},
        ],
        "task": [
            {"entity_id": "e1"},
            {"entity_id": "e2"},
        ],
        "parent": [
            {"entity_id": "e2", "source": "e2", "target": "e1"},
        ],
        "schema": [
            {
                "entity_id": "description",
                "columns": {"value": {"type": "str"}},
            },
            {
                "entity_id": "task",
                "columns": {},
            },
        ],
    }


@pytest.fixture
def sample_schema_list():
    """Schema component as a list of instances."""
    return [
        {
            "entity_id": "value",
            "columns": {"value": {"type": "str"}},
            "parent": None,
        },
        {
            "entity_id": "description",
            "columns": {"value": {"type": "str"}},
            "parent": "value",
        },
        {
            "entity_id": "task",
            "columns": {},
            "parent": "value",
        },
    ]


@pytest.fixture
def sample_parent_list():
    """Parent component as a list of instances."""
    return [
        {"entity_id": "description", "source": "description", "target": "value"},
        {"entity_id": "task", "source": "task", "target": "value"},
    ]


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
# flattened_entity_first_data
# ---------------------------------------------------------------------------

class TestFlattenedEntityFirstData:

    def test_flat_data_unchanged(self):
        """Data with no nesting should pass through largely unchanged."""
        data = {
            "my_task": [
                {"description": "A task."},
                "task",
            ],
        }
        result = flattened_entity_first_data(data)
        flattened = result["flattened_data"]
        task_id = dhash("my_task")
        assert task_id in flattened
        assert isinstance(flattened[task_id], list)

    def test_name_to_id_mapping_returned(self):
        """Should return a name_to_id mapping alongside flattened data."""
        data = {
            "my_task": [
                {"description": "A task."},
            ],
        }
        result = flattened_entity_first_data(data)
        assert "name_to_id" in result
        assert "my_task" in result["name_to_id"]
        assert result["name_to_id"]["my_task"] == dhash("my_task")

    def test_nested_entities_are_flattened(self, nested_entity_data):
        result = flattened_entity_first_data(nested_entity_data)
        flattened = result["flattened_data"]
        core_id = dhash("core_task")
        assert core_id in flattened
        child_keys = [k for k in flattened if k != core_id]
        assert len(child_keys) >= 1, "Child entity should be flattened to top level"

    def test_parent_components_added(self, nested_entity_data):
        """Flattening should add parent components to child entities."""
        result = flattened_entity_first_data(nested_entity_data)
        flattened = result["flattened_data"]
        core_id = dhash("core_task")
        child_keys = [k for k in flattened if k != core_id]
        assert len(child_keys) >= 1
        child_components = flattened[child_keys[0]]
        parent_refs = [
            c for c in child_components
            if isinstance(c, dict) and "parent" in c
        ]
        assert len(parent_refs) >= 1, "Child should have a parent component"

    def test_returns_dict(self, nested_entity_data):
        result = flattened_entity_first_data(nested_entity_data)
        flattened = result["flattened_data"]
        assert isinstance(flattened, dict)
        for v in flattened.values():
            assert isinstance(v, list), "Each entity value should be a component list"


# ---------------------------------------------------------------------------
# component_first_data
# ---------------------------------------------------------------------------

class TestComponentFirstData:

    def test_returns_dict_of_lists(self, flat_entity_data, flat_entity_name_to_id):
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        assert isinstance(result, dict)
        for v in result.values():
            assert isinstance(v, list)

    def test_contains_schema_key(self, flat_entity_data, flat_entity_name_to_id):
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        assert "schema" in result

    def test_contains_parent_key(self, flat_entity_data, flat_entity_name_to_id):
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        assert "parent" in result

    def test_groups_by_component_type(self, flat_entity_data, flat_entity_name_to_id):
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        assert "description" in result
        assert "task" in result

    def test_contains_name_component(self, flat_entity_data, flat_entity_name_to_id):
        """Each entity should get a 'name' component with its original path."""
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        assert "name" in result
        names = {inst["value"] for inst in result["name"]}
        assert "core_task" in names
        assert "core_task.subtask_a" in names

    def test_references_resolved_to_hashed_ids(self):
        """Cross-entity references in target/value fields should be resolved to hashed IDs."""
        task_id = dhash("my_task")
        infra_id = dhash("my_infra")
        data = {
            task_id: [
                {"description": "A task."},
                "task",
            ],
            infra_id: [
                {"description": "Infrastructure."},
                {"solution of": "my_task"},
            ],
        }
        name_to_id = {"my_task": task_id, "my_infra": infra_id}
        result = component_first_data(data, name_to_id)
        sol_instances = result["solution of"]
        assert sol_instances[0]["value"] == task_id

    def test_parent_of_creates_inverse_parent(self):
        """'parent of: Y' should create a parent component with source=Y, target=current."""
        root_id = dhash("root")
        child_id = dhash("child_entity")
        data = {
            root_id: [
                {"parent of": "child_entity"},
            ],
            child_id: [
                "task",
            ],
        }
        name_to_id = {"root": root_id, "child_entity": child_id}
        result = component_first_data(data, name_to_id)
        parent_instances = result["parent"]
        assert len(parent_instances) == 1
        p = parent_instances[0]
        # "parent of" sets entity_id to the resolved child ID
        assert p["entity_id"] == child_id
        assert p["source"] == child_id
        assert p["target"] == root_id

    def test_component_instances_have_entity_id(self, flat_entity_data, flat_entity_name_to_id):
        result = component_first_data(flat_entity_data, flat_entity_name_to_id)
        for comp_type, instances in result.items():
            for instance in instances:
                assert "entity_id" in instance, (
                    f"Instance in '{comp_type}' missing entity_id"
                )


# ---------------------------------------------------------------------------
# complete_schema
# ---------------------------------------------------------------------------

class TestCompleteSchema:

    def test_returns_dict(self, sample_schema_list, sample_parent_list):
        result = complete_schema(sample_schema_list, sample_parent_list)
        assert isinstance(result, dict)

    def test_child_inherits_parent_columns(self, sample_schema_list, sample_parent_list):
        """A child schema should include columns from its parent."""
        result = complete_schema(sample_schema_list, sample_parent_list)
        # "description" inherits from "value", both have "value" column
        assert "description" in result
        desc_columns = result["description"]
        assert "value" in desc_columns or any(
            "value" in str(v) for v in desc_columns.values()
        ), "description should inherit 'value' column from parent"

    def test_parent_schema_preserved(self, sample_schema_list, sample_parent_list):
        result = complete_schema(sample_schema_list, sample_parent_list)
        assert "value" in result, "Parent schema 'value' should be present"

    def test_child_can_override_parent_columns(self):
        """If a child redefines a column from the parent, the child's version wins."""
        schema = [
            {"entity_id": "base", "columns": {"x": {"type": "str"}}, "parent": None},
            {
                "entity_id": "child",
                "columns": {"x": {"type": "int"}},
                "parent": "base",
            },
        ]
        parent = [{"entity_id": "child", "source": "child", "target": "base"}]
        result = complete_schema(schema, parent)
        # child's override should win
        assert result["child"]["x"]["type"] == "int"


# ---------------------------------------------------------------------------
# data_models
# ---------------------------------------------------------------------------

class TestDataModels:

    def test_returns_dict_of_models(self):
        schema = {
            "description": {"value": {"type": "str"}},
            "task": {},
        }
        result = data_models(schema)
        assert isinstance(result, dict)
        for v in result.values():
            assert isinstance(v, type) and issubclass(v, pydantic.BaseModel)

    def test_model_has_expected_fields(self):
        schema = {
            "description": {"value": {"type": "str"}},
        }
        result = data_models(schema)
        model = result["description"]
        assert "value" in model.model_fields

    def test_empty_schema_produces_model(self):
        """A tag component (no columns) should still produce a valid model."""
        schema = {"task": {}}
        result = data_models(schema)
        assert "task" in result
        instance = result["task"]()
        assert isinstance(instance, pydantic.BaseModel)


# ---------------------------------------------------------------------------
# components_database
# ---------------------------------------------------------------------------

class TestComponentsDatabase:

    def test_returns_conn_and_components(self):
        comp_data = {
            "description": [
                {"entity_id": "e1", "value": "Hello"},
            ],
        }
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        conn, components = components_database(comp_data, models)
        assert isinstance(conn, ibis.BaseBackend)
        assert isinstance(components, dict)

    def test_table_components_are_ibis_tables(self):
        comp_data = {
            "description": [
                {"entity_id": "e1", "value": "Hello"},
            ],
        }
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        conn, components = components_database(comp_data, models)
        assert isinstance(components["description"], ibis.Table)

    def test_complex_values_kept_as_raw_list(self):
        """Components with dict/list values should be kept as raw lists, not ibis Tables."""
        comp_data = {
            "schema": [
                {"entity_id": "description", "columns": {"value": {"type": "str"}}},
            ],
        }
        model = pydantic.create_model("schema")
        models = {"schema": model}
        conn, components = components_database(comp_data, models)
        assert isinstance(components["schema"], list)
        assert not isinstance(components["schema"], ibis.Table)

    def test_table_has_expected_rows(self):
        comp_data = {
            "description": [
                {"entity_id": "e1", "value": "Hello"},
                {"entity_id": "e2", "value": "World"},
            ],
        }
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        conn, components = components_database(comp_data, models)
        df = components["description"].to_pandas()
        assert len(df) == 2


# ---------------------------------------------------------------------------
# validated_components
# ---------------------------------------------------------------------------

class TestValidatedComponents:

    def test_returns_dict(self):
        con = ibis.duckdb.connect()
        table = con.create_table(
            "desc", {"entity_id": ["e1"], "value": ["Hello"]}
        )
        comps = {"description": table}
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        result = validated_components(comps, models)
        assert isinstance(result, dict)
        assert "description" in result

    def test_schema_stored_in_result(self):
        con = ibis.duckdb.connect()
        table = con.create_table(
            "desc", {"entity_id": ["e1"], "value": ["Hello"]}
        )
        comps = {"description": table}
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        result = validated_components(comps, models)
        assert "schema" in result, "Data models should be stored under 'schema' key"

    def test_valid_data_passes(self):
        """Components matching their schema should pass validation without error."""
        con = ibis.duckdb.connect()
        table = con.create_table(
            "desc", {"entity_id": ["e1"], "value": ["Hello"]}
        )
        comps = {"description": table}
        model = pydantic.create_model("description", value=(str, ...))
        models = {"description": model}
        # Should not raise
        validated_components(comps, models)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_returns_registry_instance(self):
        con = ibis.duckdb.connect()
        con.create_table("description", {"entity_id": ["e1"], "value": ["Hello"]})
        comps = {"description": con.table("description")}
        result = registry(con, comps)
        assert isinstance(result, Registry)

    def test_registry_has_component_types(self):
        con = ibis.duckdb.connect()
        con.create_table("description", {"entity_id": ["e1"], "value": ["Hello"]})
        con.create_table("task", {"entity_id": ["e1"]})
        comps = {
            "description": con.table("description"),
            "task": con.table("task"),
        }
        result = registry(con, comps)
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
