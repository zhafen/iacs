"""Tests for the manifest_to_registry Hamilton DAG functions."""

import os
import tempfile
from pathlib import Path

import ibis
import pydantic
import pytest

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
from iacs.registry import Registry


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
    """Flattened entity-first data (no hierarchy, parent components added)."""
    return {
        "core_task": [
            {"description": "The main task."},
            "task",
        ],
        "core_task.subtask_a": [
            {"description": "A subtask."},
            "task",
            {"parent": "core_task"},
        ],
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
        result = raw_entity_first_data(minimal_yaml_dir)
        assert isinstance(result, dict)
        assert "my_task" in result

    def test_loads_multiple_yaml_files(self, multi_file_yaml_dir):
        result = raw_entity_first_data(multi_file_yaml_dir)
        assert isinstance(result, dict)
        assert "my_task" in result
        assert "my_infra" in result

    def test_loads_yaml_from_subdirectories(self, multi_file_yaml_dir):
        result = raw_entity_first_data(multi_file_yaml_dir)
        # my_infra is in a subdirectory
        assert "my_infra" in result

    def test_returns_empty_dict_for_empty_dir(self, tmp_path):
        result = raw_entity_first_data(str(tmp_path))
        assert result == {}

    def test_preserves_raw_structure(self, minimal_yaml_dir):
        result = raw_entity_first_data(minimal_yaml_dir)
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
        assert "my_task" in result
        assert isinstance(result["my_task"], list)

    def test_nested_entities_are_flattened(self, nested_entity_data):
        result = flattened_entity_first_data(nested_entity_data)
        # Parent entity should be present
        assert "core_task" in result
        # Child entity should be present with dotted path or similar key
        child_keys = [k for k in result if k != "core_task"]
        assert len(child_keys) >= 1, "Child entity should be flattened to top level"

    def test_parent_components_added(self, nested_entity_data):
        """Flattening should add parent components to child entities."""
        result = flattened_entity_first_data(nested_entity_data)
        # Find the child entity's components
        child_keys = [k for k in result if k != "core_task"]
        assert len(child_keys) >= 1
        child_components = result[child_keys[0]]
        # Should contain a parent reference
        parent_refs = [
            c for c in child_components
            if isinstance(c, dict) and "parent" in c
        ]
        assert len(parent_refs) >= 1, "Child should have a parent component"

    def test_returns_dict(self, nested_entity_data):
        result = flattened_entity_first_data(nested_entity_data)
        assert isinstance(result, dict)
        for v in result.values():
            assert isinstance(v, list), "Each entity value should be a component list"


# ---------------------------------------------------------------------------
# component_first_data
# ---------------------------------------------------------------------------

class TestComponentFirstData:

    def test_returns_dict_of_lists(self, flat_entity_data):
        result = component_first_data(flat_entity_data)
        assert isinstance(result, dict)
        for v in result.values():
            assert isinstance(v, list)

    def test_contains_schema_key(self, flat_entity_data):
        result = component_first_data(flat_entity_data)
        assert "schema" in result

    def test_contains_parent_key(self, flat_entity_data):
        result = component_first_data(flat_entity_data)
        assert "parent" in result

    def test_groups_by_component_type(self, flat_entity_data):
        result = component_first_data(flat_entity_data)
        # Should have description and task component types
        assert "description" in result
        assert "task" in result

    def test_component_instances_have_entity_id(self, flat_entity_data):
        result = component_first_data(flat_entity_data)
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
