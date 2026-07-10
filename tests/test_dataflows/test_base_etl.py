"""Tests for the base_etl Hamilton DAG functions."""

import ibis
import pandas as pd
import pytest

import iacs.dataflows.base_etl as base_etl
from iacs.registry import Registry


@pytest.fixture
def scd_registry_with_nulls():
    """A registry with a "status_reading" type whose "as_of" field is time_dimension."""
    conn = ibis.duckdb.connect()
    conn.create_table(
        "entity_id",
        {"value": ["def1"], "alias": ["status_reading"], "path": ["test:status_reading"],
         "entity_key": ["status_reading"], "filepath": ["test"]},
    )
    conn.create_table(
        "derived_field",
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
        "derived_field": conn.table("derived_field"),
        "status_reading": conn.table("status_reading"),
    }
    return Registry(conn, components)


class TestTimeFilledRegistry:
    """Tests for the time_filled_registry node."""

    def test_no_load_time_is_noop(self, scd_registry_with_nulls):
        result = base_etl.time_filled_registry(scd_registry_with_nulls, load_time=None)
        df = result.get("status_reading").execute()
        assert pd.isna(df.set_index("entity_id").loc["e1", "as_of"])

    def test_fills_null_time_dimension_values(self, scd_registry_with_nulls):
        result = base_etl.time_filled_registry(scd_registry_with_nulls, load_time="2024-12-25")
        df = result.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e1", "as_of"] == "2024-12-25"

    def test_does_not_overwrite_existing_values(self, scd_registry_with_nulls):
        result = base_etl.time_filled_registry(scd_registry_with_nulls, load_time="2024-12-25")
        df = result.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e2", "as_of"] == "2024-01-01"

    def test_leaves_non_time_dimension_fields_untouched(self, scd_registry_with_nulls):
        result = base_etl.time_filled_registry(scd_registry_with_nulls, load_time="2024-12-25")
        df = result.get("status_reading").execute()
        assert df.set_index("entity_id").loc["e1", "status"] == "open"

    def test_returns_same_registry_instance(self, scd_registry_with_nulls):
        result = base_etl.time_filled_registry(scd_registry_with_nulls, load_time="2024-12-25")
        assert result is scd_registry_with_nulls

    def test_multiple_time_dimension_fields_raises(self, scd_registry_with_nulls):
        """Only one time_dimension field is allowed per component type."""
        conn = scd_registry_with_nulls._con
        conn.create_table(
            "derived_field",
            {"entity_id": ["def1", "def1"], "value": ["as_of", "also_as_of"],
             "time_dimension": [True, True]},
            overwrite=True,
        )
        scd_registry_with_nulls._components["derived_field"] = conn.table("derived_field")
        with pytest.raises(ValueError, match="status_reading"):
            base_etl.time_filled_registry(scd_registry_with_nulls, load_time="2024-12-25")


class TestRegistryNode:
    """Tests for the final registry passthrough node."""

    def test_passes_through_time_filled_registry(self, scd_registry_with_nulls):
        result = base_etl.registry(scd_registry_with_nulls)
        assert result is scd_registry_with_nulls
