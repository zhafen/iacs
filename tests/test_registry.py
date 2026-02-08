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
