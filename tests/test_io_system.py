import pandas as pd
import pytest

from iacs.io_system import IOSystem


class TestIOSystemBasics:
    """Tests for basic IOSystem functionality."""

    def test_read_empty_data_returns_empty_dataframe(self):
        """Reading empty entity-centered data produces an empty dataframe."""
        system = IOSystem()
        result = system.read_entity_centered({})

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_read_entity_centered_returns_expected_columns(self):
        """Read dataframe has the expected columns."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "A simple entity."},
            ]
        }

        result = system.read_entity_centered(data)

        assert "entity_id" in result.columns
        assert "component_index" in result.columns
        assert "component_type" in result.columns
        assert "component_value" in result.columns


class TestIOSystemSingleEntity:
    """Tests for reading single entities."""

    def test_read_entity_with_single_value_component(self):
        """Read an entity with a single value component."""
        system = IOSystem()
        data = {
            "my_entity": [
                {"description": "A simple entity."},
            ]
        }

        result = system.read_entity_centered(data)

        assert len(result) == 1
        row = result.iloc[0]
        assert row["entity_id"] == "my_entity"
        assert row["component_index"] == 0
        assert row["component_type"] == "description"
        assert row["component_value"] == {"value": "A simple entity."}

    def test_read_entity_with_tag_component(self):
        """Read an entity with a tag component (string, no value)."""
        system = IOSystem()
        data = {
            "my_task": [
                "task",
            ]
        }

        result = system.read_entity_centered(data)

        assert len(result) == 1
        row = result.iloc[0]
        assert row["entity_id"] == "my_task"
        assert row["component_index"] == 0
        assert row["component_type"] == "task"
        assert row["component_value"] == {}

    def test_read_entity_with_multiple_components(self):
        """Read an entity with multiple components."""
        system = IOSystem()
        data = {
            "my_task": [
                {"description": "A task I need to complete."},
                "task",
            ]
        }

        result = system.read_entity_centered(data)

        assert len(result) == 2
        assert result.iloc[0]["component_index"] == 0
        assert result.iloc[0]["component_type"] == "description"
        assert result.iloc[1]["component_index"] == 1
        assert result.iloc[1]["component_type"] == "task"


class TestIOSystemMultipleEntities:
    """Tests for reading multiple entities."""

    def test_read_multiple_entities(self):
        """Read multiple entities from entity-centered data."""
        system = IOSystem()
        data = {
            "entity_a": [
                {"description": "First entity."},
            ],
            "entity_b": [
                {"description": "Second entity."},
            ],
        }

        result = system.read_entity_centered(data)

        assert len(result) == 2
        entity_ids = result["entity_id"].tolist()
        assert "entity_a" in entity_ids
        assert "entity_b" in entity_ids


class TestIOSystemMinimalExample:
    """Tests for reading the minimal example."""

    def test_read_minimal_example(self):
        """Read the minimal example data."""
        system = IOSystem()
        data = {
            "my_task": [
                {"description": "A task I need to complete."},
                "task",
            ],
            "my_infrastructure": [
                {"description": "Infrastructure to complete the task."},
                {"implements": "my_task"},
            ],
        }

        result = system.read_entity_centered(data)

        assert len(result) == 4

        # Check my_task components
        my_task_rows = result[result["entity_id"] == "my_task"]
        assert len(my_task_rows) == 2

        description_row = my_task_rows[
            my_task_rows["component_type"] == "description"
        ].iloc[0]
        assert description_row["component_value"] == {
            "value": "A task I need to complete."
        }

        task_row = my_task_rows[my_task_rows["component_type"] == "task"].iloc[0]
        assert task_row["component_value"] == {}

        # Check my_infrastructure components
        infra_rows = result[result["entity_id"] == "my_infrastructure"]
        assert len(infra_rows) == 2

        implements_row = infra_rows[
            infra_rows["component_type"] == "implements"
        ].iloc[0]
        assert implements_row["component_value"] == {"value": "my_task"}

    def test_read_from_file(self, tmp_path):
        """Read from an actual file path."""
        file_content = """my_task:
- description: A task I need to complete.
- task
"""
        file_path = tmp_path / "test.yaml"
        file_path.write_text(file_content)

        system = IOSystem()
        result = system.read_entity_centered_file(file_path)

        assert len(result) == 2
        assert result.iloc[0]["entity_id"] == "my_task"


class TestComponentCenteredBasics:
    """Tests for converting to component-centered format."""

    def test_to_component_centered_returns_registry(self):
        """to_component_centered returns a Registry."""
        from iacs.registry import Registry

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        result = system.to_component_centered(entity_centered)

        assert isinstance(result, Registry)

    def test_to_component_centered_creates_table_per_component_type(self):
        """Each component type gets its own table in the registry."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_task": [
                {"description": "A task."},
                "task",
            ]
        })

        registry = system.to_component_centered(entity_centered)

        assert "description" in registry.component_types
        assert "task" in registry.component_types

    def test_empty_entity_centered_produces_empty_registry(self):
        """Empty entity-centered data produces empty registry."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({})

        registry = system.to_component_centered(entity_centered)

        assert len(registry.component_types) == 0


class TestComponentCenteredTableStructure:
    """Tests for component table structure in component-centered format."""

    def test_component_table_has_multi_index(self):
        """Component tables have multi-index of (entity_id, component_index)."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("description")

        assert table.index.names == ["entity_id", "component_index"]

    def test_component_table_has_component_type_column(self):
        """Component tables have a component_type column."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("description")

        assert "component_type" in table.columns

    def test_component_table_has_value_column_for_value_components(self):
        """Value component tables have a value column."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("description")

        assert "value" in table.columns
        assert table.loc[("my_entity", 0), "value"] == "A simple entity."

    def test_tag_component_table_has_no_value_column(self):
        """Tag component tables have component_type but no value column."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_task": ["task"]
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("task")

        assert "component_type" in table.columns
        # Tag components have no value column (or empty component_value)
        assert len(table) == 1


class TestComponentCenteredMultipleEntities:
    """Tests for component-centered format with multiple entities."""

    def test_same_component_type_from_multiple_entities(self):
        """Components of same type from different entities in same table."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "entity_a": [{"description": "First entity."}],
            "entity_b": [{"description": "Second entity."}],
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("description")

        assert len(table) == 2
        assert ("entity_a", 0) in table.index
        assert ("entity_b", 0) in table.index

    def test_multiple_components_same_type_same_entity(self):
        """Multiple components of same type on one entity have different indices."""
        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [
                {"description": "First description."},
                {"description": "Second description."},
            ]
        })

        registry = system.to_component_centered(entity_centered)
        table = registry.view("description")

        assert len(table) == 2
        assert table.loc[("my_entity", 0), "value"] == "First description."
        assert table.loc[("my_entity", 1), "value"] == "Second description."
