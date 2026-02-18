import ibis
import pandas as pd
import pytest

from iacs.registry import Registry


class TestRegistryInitialization:
    """Tests for initializing a Registry with a connection and components."""

    def test_init_with_single_component(self):
        """Registry can be initialized with a single component table."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["iacs", "registry"], "value": ["A tool for architects", "Stores ECS data"]},
        )
        components = {"description": conn.table("description")}

        registry = Registry(conn, components)

        assert "description" in registry.component_types
        assert "description" in registry._con.list_tables()

    def test_init_with_multiple_components(self):
        """Registry can be initialized with multiple component tables."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["iacs"], "value": ["A tool for architects"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["iacs"], "value": ["functional"], "priority": [1.0]},
        )
        components = {
            "description": conn.table("description"),
            "requirement": conn.table("requirement"),
        }

        registry = Registry(conn, components)

        assert "description" in registry.component_types
        assert "requirement" in registry.component_types

    def test_init_with_empty_dict_creates_empty_registry(self):
        """Registry can be initialized with an empty dict."""
        conn = ibis.duckdb.connect()
        registry = Registry(conn, {})

        assert len(registry.component_types) == 0

    def test_schema_key_excluded_from_component_types(self):
        """The 'schema' key in components is not treated as a component type."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["e1"], "value": ["Hello"]},
        )
        components = {
            "description": conn.table("description"),
            "schema": {"description": object},
        }

        registry = Registry(conn, components)

        assert "description" in registry.component_types
        assert "schema" not in registry.component_types


class TestRegistryView:
    """Tests for viewing components in the Registry."""

    @pytest.fixture
    def sample_registry(self):
        """Create a registry with sample data for testing."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["iacs", "registry"], "value": ["A tool for architects", "Stores ECS data"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["iacs", "iacs"], "value": ["functional", "quality"], "priority": [1.0, 0.5]},
        )
        components = {
            "description": conn.table("description"),
            "requirement": conn.table("requirement"),
        }
        return Registry(conn, components)

    def test_view_returns_ibis_table(self, sample_registry):
        """view() returns an ibis Table for the specified component type."""
        result = sample_registry.view("description")
        assert isinstance(result, ibis.Table)

    def test_view_returns_correct_data(self, sample_registry):
        """view() returns the correct data for the component."""
        result = sample_registry.view_df("requirement")

        assert "value" in result.columns
        assert "priority" in result.columns

    def test_view_nonexistent_component_raises_keyerror(self, sample_registry):
        """view() raises KeyError for a component type that doesn't exist."""
        with pytest.raises(KeyError):
            sample_registry.view("nonexistent")

    def test_view_returns_copy_not_reference(self, sample_registry):
        """view_df() returns a copy to prevent accidental modification."""
        result = sample_registry.view_df("description")
        result.loc["iacs", "value"] = "Modified"

        original = sample_registry.view_df("description")
        assert original.loc["iacs", "value"] == "A tool for architects"


class TestRegistryViewMultipleComponents:
    """Tests for viewing multiple components joined by entity_id."""

    @pytest.fixture
    def multi_component_registry(self):
        """Create a registry with entities having multiple component types."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["a", "b", "c"], "value": ["Desc A", "Desc B", "Desc C"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["a", "b"]},
        )
        components = {
            "description": conn.table("description"),
            "requirement": conn.table("requirement"),
        }
        return Registry(conn, components)

    def test_view_multiple_components_returns_dataframe(self, multi_component_registry):
        """view() with list of components returns a DataFrame."""
        result = multi_component_registry.view_df(["description", "requirement"])
        assert isinstance(result, pd.DataFrame)

    def test_view_multiple_components_inner_joins_by_entity_id(self, multi_component_registry):
        """view() with list of components inner joins by entity_id."""
        result = multi_component_registry.view_df(["description", "requirement"])

        # entity c has no requirement, so it should be excluded
        entity_ids = result.index.unique()
        assert "a" in entity_ids
        assert "b" in entity_ids
        assert "c" not in entity_ids

    def test_view_single_component_as_list_works(self, multi_component_registry):
        """view() with single-element list works like single string."""
        result = multi_component_registry.view_df(["description"])
        assert isinstance(result, pd.DataFrame)
        assert "value" in result.columns
