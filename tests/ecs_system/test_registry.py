import pandas as pd
import pytest

from iacs.registry import Registry


class TestRegistryInitialization:
    """Tests for initializing a Registry from component dataframes."""

    def test_init_with_single_component_dataframe(self):
        """Registry can be initialized with a single component dataframe."""
        description_df = pd.DataFrame(
            {"value": ["A tool for architects", "Stores ECS data"]},
            index=pd.MultiIndex.from_tuples(
                [("iacs", 0), ("registry", 0)],
                names=["entity_id", "component_index"],
            ),
        )

        registry = Registry({"description": description_df})

        assert "description" in registry.component_types

    def test_init_with_multiple_component_dataframes(self):
        """Registry can be initialized with multiple component dataframes."""
        description_df = pd.DataFrame(
            {"value": ["A tool for architects"]},
            index=pd.MultiIndex.from_tuples(
                [("iacs", 0)],
                names=["entity_id", "component_index"],
            ),
        )
        requirement_df = pd.DataFrame(
            {"value": ["functional"], "priority": [1.0]},
            index=pd.MultiIndex.from_tuples(
                [("iacs", 0)],
                names=["entity_id", "component_index"],
            ),
        )

        registry = Registry({
            "description": description_df,
            "requirement": requirement_df,
        })

        assert "description" in registry.component_types
        assert "requirement" in registry.component_types

    def test_init_with_empty_dict_creates_empty_registry(self):
        """Registry can be initialized with an empty dict."""
        registry = Registry({})

        assert len(registry.component_types) == 0

    def test_init_preserves_dataframe_index_structure(self):
        """Registry preserves the multi-index structure of component dataframes."""
        description_df = pd.DataFrame(
            {"value": ["First description", "Second description"]},
            index=pd.MultiIndex.from_tuples(
                [("entity_a", 0), ("entity_a", 1)],
                names=["entity_id", "component_index"],
            ),
        )

        registry = Registry({"description": description_df})

        stored_df = registry.view("description")
        assert stored_df.index.names == ["entity_id", "component_index"]
        assert len(stored_df) == 2


class TestRegistryView:
    """Tests for viewing components in the Registry."""

    @pytest.fixture
    def sample_registry(self):
        """Create a registry with sample data for testing."""
        description_df = pd.DataFrame(
            {"value": ["A tool for architects", "Stores ECS data"]},
            index=pd.MultiIndex.from_tuples(
                [("iacs", 0), ("registry", 0)],
                names=["entity_id", "component_index"],
            ),
        )
        requirement_df = pd.DataFrame(
            {"value": ["functional", "quality"], "priority": [1.0, 0.5]},
            index=pd.MultiIndex.from_tuples(
                [("iacs", 0), ("iacs", 1)],
                names=["entity_id", "component_index"],
            ),
        )
        return Registry({
            "description": description_df,
            "requirement": requirement_df,
        })

    def test_view_returns_component_dataframe(self, sample_registry):
        """view() returns the dataframe for the specified component type."""
        result = sample_registry.view("description")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2

    def test_view_returns_correct_data(self, sample_registry):
        """view() returns the correct data for the component."""
        result = sample_registry.view("requirement")

        assert "value" in result.columns
        assert "priority" in result.columns
        assert result.loc[("iacs", 0), "value"] == "functional"
        assert result.loc[("iacs", 1), "priority"] == 0.5

    def test_view_nonexistent_component_raises_keyerror(self, sample_registry):
        """view() raises KeyError for a component type that doesn't exist."""
        with pytest.raises(KeyError):
            sample_registry.view("nonexistent")

    def test_view_returns_copy_not_reference(self, sample_registry):
        """view() returns a copy to prevent accidental modification."""
        result = sample_registry.view("description")
        result.loc[("iacs", 0), "value"] = "Modified"

        original = sample_registry.view("description")
        assert original.loc[("iacs", 0), "value"] == "A tool for architects"


class TestRegistryFromEntityCentered:
    """Tests for constructing Registry from entity-centered data."""

    def test_from_entity_centered_returns_registry(self):
        """from_entity_centered returns a Registry."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        result = Registry.from_entity_centered(entity_centered)

        assert isinstance(result, Registry)

    def test_from_entity_centered_creates_table_per_component_type(self):
        """Each component type gets its own table in the registry."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_task": [
                {"description": "A task."},
                "task",
            ]
        })

        registry = Registry.from_entity_centered(entity_centered)

        assert "description" in registry.component_types
        assert "task" in registry.component_types

    def test_from_entity_centered_empty_produces_empty_registry(self):
        """Empty entity-centered data produces empty registry."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({})

        registry = Registry.from_entity_centered(entity_centered)

        assert len(registry.component_types) == 0


class TestRegistryFromEntityCenteredTableStructure:
    """Tests for component table structure when constructed from entity-centered."""

    def test_component_table_has_multi_index(self):
        """Component tables have multi-index of (entity_id, component_index)."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("description")

        assert table.index.names == ["entity_id", "component_index"]

    def test_component_table_has_component_type_column(self):
        """Component tables have a component_type column."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("description")

        assert "component_type" in table.columns

    def test_component_table_has_value_column_for_value_components(self):
        """Value component tables have a value column."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "A simple entity."}]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("description")

        assert "value" in table.columns
        assert table.loc[("my_entity", 0), "value"] == "A simple entity."

    def test_tag_component_table_has_no_value_column(self):
        """Tag component tables have component_type but no value column."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_task": ["task"]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("task")

        assert "component_type" in table.columns
        assert len(table) == 1


class TestRegistryFromEntityCenteredMultipleEntities:
    """Tests for from_entity_centered with multiple entities."""

    def test_same_component_type_from_multiple_entities(self):
        """Components of same type from different entities in same table."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "entity_a": [{"description": "First entity."}],
            "entity_b": [{"description": "Second entity."}],
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("description")

        assert len(table) == 2
        assert ("entity_a", 0) in table.index
        assert ("entity_b", 0) in table.index

    def test_multiple_components_same_type_same_entity(self):
        """Multiple components of same type on one entity have different indices."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [
                {"description": "First description."},
                {"description": "Second description."},
            ]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("description")

        assert len(table) == 2
        assert table.loc[("my_entity", 0), "value"] == "First description."
        assert table.loc[("my_entity", 1), "value"] == "Second description."
