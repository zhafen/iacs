import pandas as pd

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
