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
            {"entity_id": ["iacs"], "type": ["functional"], "value": [1.0]},
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

    def test_non_table_components_excluded_from_component_types(self):
        """Components that are raw lists (not ibis Tables) should be excluded from component_types."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["e1"], "value": ["Hello"]},
        )
        components = {
            "description": conn.table("description"),
            "schema_comp": [{"entity_id": "description", "columns": {"value": {"type": "str"}}}],
        }

        registry = Registry(conn, components)

        assert "description" in registry.component_types
        assert "schema_comp" not in registry.component_types

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
            "entity_id",
            {"value": ["iacs", "registry"], "alias": ["iacs", "registry"],
             "path": ["test:iacs", "test:registry"], "entity_key": ["iacs", "registry"],
             "filepath": ["test", "test"]},
        )
        conn.create_table(
            "description",
            {"entity_id": ["iacs", "registry"], "value": ["A tool for architects", "Stores ECS data"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["iacs", "iacs"], "type": ["functional", "quality"], "value": [1.0, 0.5]},
        )
        components = {
            "entity_id": conn.table("entity_id"),
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

        assert "requirement.value" in result.columns
        assert "requirement.type" in result.columns

    def test_view_nonexistent_component_raises_keyerror(self, sample_registry):
        """view() raises KeyError for a component type that doesn't exist."""
        with pytest.raises(KeyError):
            sample_registry.view("nonexistent")

    def test_view_returns_copy_not_reference(self, sample_registry):
        """view_df() returns a copy to prevent accidental modification."""
        result = sample_registry.view_df("description")
        result.loc["iacs", "description.value"] = "Modified"

        original = sample_registry.view_df("description")
        assert original.loc["iacs", "description.value"] == "A tool for architects"


class TestRegistryViewMultipleComponents:
    """Tests for viewing multiple components joined by entity_id."""

    @pytest.fixture
    def multi_component_registry(self):
        """Create a registry with entities having multiple component types."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "entity_id",
            {"value": ["a", "b", "c"], "alias": ["a", "b", "c"],
             "path": ["test:a", "test:b", "test:c"], "entity_key": ["a", "b", "c"],
             "filepath": ["test", "test", "test"]},
        )
        conn.create_table(
            "description",
            {"entity_id": ["a", "b", "c"], "value": ["Desc A", "Desc B", "Desc C"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["a", "b"], "value": [1.0, 0.0]},
        )
        components = {
            "entity_id": conn.table("entity_id"),
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

    def test_view_specific_fields(self, multi_component_registry):

        result = multi_component_registry.view_df(["description.value", "requirement.value"])
        assert result.loc["b", "description.value"] == "Desc B"
        assert result.loc["b", "requirement.value"] == 0.0

    def test_view_single_component_as_list_works(self, multi_component_registry):
        """view() with single-element list works like single string."""
        result = multi_component_registry.view_df(["description"])
        assert isinstance(result, pd.DataFrame)
        assert "description.value" in result.columns


class TestRegistryViewCurrent:
    """Tests for view_current(), which collapses slowly changing dimensions."""

    @pytest.fixture
    def scd_registry(self):
        """A registry with a "status_reading" type whose "as_of" field is time_dimension."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "entity_id",
            {"value": ["def1", "e1", "e2"], "alias": ["status_reading", "e1", "e2"],
             "path": ["test:status_reading", "test:e1", "test:e2"],
             "entity_key": ["status_reading", "e1", "e2"], "filepath": ["test", "test", "test"]},
        )
        conn.create_table(
            "field",
            {"entity_id": ["def1", "def1"], "value": ["as_of", "status"],
             "time_dimension": [True, False]},
        )
        conn.create_table(
            "status_reading",
            {"entity_id": ["e1", "e1", "e2"],
             "component_index": [0, 0, 0],
             "modifier": pd.array([None, None, None], dtype=pd.StringDtype()),
             "as_of": ["2024-01-01", "2024-06-01", "2024-03-01"],
             "status": ["open", "closed", "open"]},
        )
        components = {
            "entity_id": conn.table("entity_id"),
            "field": conn.table("field"),
            "status_reading": conn.table("status_reading"),
        }
        return Registry(conn, components)

    def test_time_dimension_fields_detected(self, scd_registry):
        assert scd_registry._time_dimension_fields("status_reading") == ["as_of"]

    def test_non_time_dimension_component_has_no_fields(self, scd_registry):
        assert scd_registry._time_dimension_fields("entity_id") == []

    def test_view_current_keeps_one_row_per_entity(self, scd_registry):
        df = scd_registry.view_current("status_reading").execute()
        assert sorted(df["entity_id"]) == ["e1", "e2"]

    def test_view_current_picks_max_time_dimension(self, scd_registry):
        df = scd_registry.view_current("status_reading").execute()
        e1_row = df[df["entity_id"] == "e1"].iloc[0]
        assert e1_row["status_reading.as_of"] == "2024-06-01"
        assert e1_row["status_reading.status"] == "closed"

    def test_view_unchanged_still_returns_all_versions(self, scd_registry):
        """view() (unlike view_current()) does not collapse SCD history."""
        df = scd_registry.view("status_reading").execute()
        as_of_values = set(df.loc[df["entity_id"] == "e1", "status_reading.as_of"])
        assert as_of_values == {"2024-01-01", "2024-06-01"}

    def test_view_current_nonexistent_component_raises_keyerror(self, scd_registry):
        with pytest.raises(KeyError):
            scd_registry.view_current("nonexistent")

    def test_view_current_component_without_time_dimension_is_unchanged(self):
        """Component types with no time_dimension fields are returned as-is."""
        conn = ibis.duckdb.connect()
        conn.create_table(
            "entity_id",
            {"value": ["e1"], "alias": ["e1"], "path": ["test:e1"],
             "entity_key": ["e1"], "filepath": ["test"]},
        )
        conn.create_table(
            "description",
            {"entity_id": ["e1", "e1"], "component_index": [0, 1],
             "modifier": pd.array([None, None], dtype=pd.StringDtype()),
             "value": ["First", "Second"]},
        )
        registry = Registry(conn, {
            "entity_id": conn.table("entity_id"),
            "description": conn.table("description"),
        })
        df = registry.view_current("description").execute()
        assert len(df) == 2


class TestRegistryFillTimeDimension:
    """Tests for fill_time_dimension()."""

    @pytest.fixture
    def scd_registry_with_nulls(self):
        conn = ibis.duckdb.connect()
        conn.create_table(
            "entity_id",
            {"value": ["def1"], "alias": ["status_reading"], "path": ["test:status_reading"],
             "entity_key": ["status_reading"], "filepath": ["test"]},
        )
        conn.create_table(
            "field",
            {"entity_id": ["def1", "def1"], "value": ["as_of", "status"],
             "time_dimension": [True, False]},
        )
        conn.create_table(
            "status_reading",
            {"entity_id": ["e1", "e2"],
             "component_index": [0, 0],
             "modifier": pd.array([None, None], dtype=pd.StringDtype()),
             "as_of": [None, "2024-01-01"],
             "status": ["open", "closed"]},
        )
        components = {
            "entity_id": conn.table("entity_id"),
            "field": conn.table("field"),
            "status_reading": conn.table("status_reading"),
        }
        return Registry(conn, components)

    def test_fills_null_time_dimension_values(self, scd_registry_with_nulls):
        scd_registry_with_nulls.fill_time_dimension("2024-12-25")
        df = scd_registry_with_nulls.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e1", "as_of"] == "2024-12-25"

    def test_does_not_overwrite_existing_values(self, scd_registry_with_nulls):
        scd_registry_with_nulls.fill_time_dimension("2024-12-25")
        df = scd_registry_with_nulls.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e2", "as_of"] == "2024-01-01"

    def test_leaves_non_time_dimension_fields_untouched(self, scd_registry_with_nulls):
        scd_registry_with_nulls.fill_time_dimension("2024-12-25")
        df = scd_registry_with_nulls.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e1", "status"] == "open"


class TestRegistryDatabaseRoundTrip:
    """Tests for exporting/loading a Registry to/from a database via ibis.connect."""

    @pytest.fixture
    def sample_registry(self):
        conn = ibis.duckdb.connect()
        conn.create_table(
            "description",
            {"entity_id": ["iacs", "registry"], "value": ["A tool for architects", "Stores ECS data"]},
        )
        conn.create_table(
            "requirement",
            {"entity_id": ["iacs"], "type": ["functional"], "value": [1.0]},
        )
        components = {
            "description": conn.table("description"),
            "requirement": conn.table("requirement"),
        }
        return Registry(conn, components)

    def test_to_database_creates_duckdb_file(self, sample_registry, tmp_path):
        db_path = tmp_path / "registry.duckdb"
        sample_registry.to_database(db_path)
        assert db_path.exists()

    def test_from_database_recovers_component_types(self, sample_registry, tmp_path):
        db_path = tmp_path / "registry.duckdb"
        sample_registry.to_database(db_path)

        loaded = Registry.from_database(db_path)

        assert set(loaded.component_types) == set(sample_registry.component_types)

    def test_from_database_recovers_data(self, sample_registry, tmp_path):
        db_path = tmp_path / "registry.duckdb"
        sample_registry.to_database(db_path)

        loaded = Registry.from_database(db_path)

        pd.testing.assert_frame_equal(
            loaded.get("description").execute().sort_values("entity_id").reset_index(drop=True),
            sample_registry.get("description").execute().sort_values("entity_id").reset_index(drop=True),
        )
