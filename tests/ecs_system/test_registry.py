import hashlib

import pandas as pd
import pytest

from iacs.registry import Registry


def eid(path: str) -> str:
    """Compute the expected entity_id for a given path (no alias)."""
    return hashlib.md5(path.encode()).hexdigest()[:12]


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
        assert "description" in registry._con.list_tables()

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
        assert "description" in registry._con.list_tables()
        assert "requirement" in registry._con.list_tables()

    def test_init_with_empty_dict_creates_empty_registry(self):
        """Registry can be initialized with an empty dict."""
        registry = Registry({})

        assert len(registry.component_types) == 0
        assert len(registry._con.list_tables()) == 0

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

        # Verify Ibis table has correct columns and row count
        ibis_table = registry._con.table("description")
        assert "entity_id" in ibis_table.columns
        assert "component_index" in ibis_table.columns
        assert "value" in ibis_table.columns
        assert ibis_table.count().execute() == 2


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
        assert "id" in registry.component_types

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
        entity_id = eid("my_entity")
        desc_row = table.loc[entity_id]
        assert "A simple entity." in desc_row["value"].values

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

        entity_ids = table.index.get_level_values("entity_id").unique()
        assert eid("entity_a") in entity_ids
        assert eid("entity_b") in entity_ids

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

        entity_id = eid("my_entity")
        desc_rows = table.loc[entity_id]
        assert len(desc_rows) == 2
        values = desc_rows["value"].tolist()
        assert "First description." in values
        assert "Second description." in values

    def test_dict_expansion(self):
        """Component value dicts are expanded into separate columns."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [
                {"metadata": {"created_by": "Alice", "created_at": "2024-01-01"}}
            ],
            "my_second_entity": [
                {"metadata": {"created_by": "Alice", "created_at": "2024-01-02"}}
            ],
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("metadata")

        assert "created_by" in table.columns
        assert "created_at" in table.columns
        entity_id = eid("my_entity")
        meta_row = table.loc[entity_id]
        assert meta_row["created_by"].iloc[0] == "Alice"
        assert meta_row["created_at"].iloc[0] == "2024-01-01"

    def test_dict_expansion_heterogeneous_components(self):
        """Component value dicts are expanded into separate columns."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [
                "requirement",
            ],
            "my_second_entity": [
                {"requirement": "constraint"}
            ],
            "my_third_entity": [
                {"requirement": {"value": "constraint", "priority": 0.8}}
            ],
            "my_fourth_entity": [
                {"requirement": {"priority": 0.4}}
            ],
        })

        registry = Registry.from_entity_centered(entity_centered)
        actual = registry.view("requirement")

        expected = pd.DataFrame([
            {"entity_id": eid("my_entity"), "component_index": 1, "component_type": "requirement", "value": None, "priority": None},
            {"entity_id": eid("my_second_entity"), "component_index": 1, "component_type": "requirement", "value": "constraint", "priority": None},
            {"entity_id": eid("my_third_entity"), "component_index": 1, "component_type": "requirement", "value": "constraint", "priority": 0.8},
            {"entity_id": eid("my_fourth_entity"), "component_index": 1, "component_type": "requirement", "value": None, "priority": 0.4},
        ]).set_index(["entity_id", "component_index"])

        pd.testing.assert_frame_equal(
            actual,
            expected
        )


class TestRegistryFromEntityCenteredIdComponent:
    """Tests for id component in registry built from entity-centered data."""

    def test_id_component_table_has_expected_columns(self):
        """The id component table has value, key, path, hash, alias columns."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "Test."}]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("id")

        assert "value" in table.columns
        assert "key" in table.columns
        assert "path" in table.columns
        assert "hash" in table.columns
        assert "alias" in table.columns

    def test_id_component_preserves_values(self):
        """The id component preserves all identity values."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "my_entity": [{"description": "Test."}]
        })

        registry = Registry.from_entity_centered(entity_centered)
        table = registry.view("id")

        entity_id = eid("my_entity")
        row = table.loc[entity_id]
        assert row["value"].iloc[0] == entity_id
        assert row["key"].iloc[0] == "my_entity"
        assert row["path"].iloc[0] == "my_entity"


class TestRegistryViewMultipleComponents:
    """Tests for viewing multiple components joined by entity_id."""

    @pytest.fixture
    def multi_component_registry(self):
        """Create a registry with entities having multiple component types."""
        from iacs.io_system import IOSystem

        system = IOSystem()
        entity_centered = system.read_entity_centered({
            "entity_a": [
                {"description": "Entity A description."},
                "requirement",
            ],
            "entity_b": [
                {"description": "Entity B description."},
                "requirement",
            ],
            "entity_c": [
                {"description": "Entity C has no requirement."},
            ],
        })
        return Registry.from_entity_centered(entity_centered)

    def test_view_multiple_components_returns_dataframe(self, multi_component_registry):
        """view() with list of components returns a DataFrame."""
        result = multi_component_registry.view(["description", "requirement"])

        assert isinstance(result, pd.DataFrame)

    def test_view_multiple_components_inner_joins_by_entity_id(self, multi_component_registry):
        """view() with list of components inner joins by entity_id."""
        result = multi_component_registry.view(["description", "requirement"])

        # entity_c has no requirement, so it should be excluded
        entity_ids = result.index.get_level_values("entity_id").unique()
        assert eid("entity_a") in entity_ids
        assert eid("entity_b") in entity_ids
        assert eid("entity_c") not in entity_ids

    def test_view_multiple_components_has_prefixed_columns(self, multi_component_registry):
        """Joined view has columns prefixed with component type."""
        result = multi_component_registry.view(["description", "requirement"])

        assert "description.value" in result.columns
        # requirement is a tag, so it has component_type but not value
        assert "requirement.component_type" in result.columns

    def test_view_multiple_components_preserves_values(self, multi_component_registry):
        """Joined view preserves the actual values from each component."""
        result = multi_component_registry.view(["description", "requirement"])

        # Check that entity_a's description value is preserved
        assert "Entity A description." in result["description.value"].values

    def test_view_single_component_as_list_works(self, multi_component_registry):
        """view() with single-element list works like single string."""
        result = multi_component_registry.view(["description"])

        assert isinstance(result, pd.DataFrame)
        assert "description.value" in result.columns
