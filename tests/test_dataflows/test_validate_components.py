"""Tests for the validate_components Hamilton DAG functions."""

import ibis
import pandas as pd
import pytest

import iacs.dataflows.validation.validate_components as validate_components


_EMPTY_FIELD_COLS = ["entity_id", "component_index", "value", "type", "nullable", "default", "range"]
_EMPTY_ENTITY_ID_COLS = ["value", "entity_key", "path", "alias"]


def _make_entity_id_table(rows: list[dict]) -> ibis.Table:
    if not rows:
        return ibis.memtable(pd.DataFrame(columns=_EMPTY_ENTITY_ID_COLS).astype(str))
    return ibis.memtable(pd.DataFrame(rows))


def _make_field_table(rows: list[dict]) -> ibis.Table:
    if not rows:
        return ibis.memtable(pd.DataFrame(columns=_EMPTY_FIELD_COLS).astype(str))
    return ibis.memtable(pd.DataFrame(rows))


def _make_component_table(rows: list[dict]) -> ibis.Table:
    return ibis.memtable(pd.DataFrame(rows))


def _call(components, field_rows, entity_id_rows):
    field = _make_field_table(field_rows)
    entity_id = _make_entity_id_table(entity_id_rows)
    return validate_components.validated_results(components, field, entity_id)


class TestValidatedComponents:

    def _entity_id_row(self, entity_id, entity_key):
        return {"value": entity_id, "entity_key": entity_key, "path": f"test:{entity_key}", "alias": entity_key}

    def _field_row(self, entity_id, field_name, field_type=None, nullable=None, default=None, field_range=None):
        return {
            "entity_id": entity_id,
            "component_index": 0,
            "value": field_name,
            "type": field_type,
            "nullable": nullable,
            "default": default,
            "range": field_range,
        }

    def test_returns_tuple(self):
        components = {"desc": _make_component_table([{"entity_id": "e1", "component_index": 0, "value": "hello"}])}
        validated, invalid = _call(components, [], [])
        assert isinstance(validated, dict)
        assert isinstance(invalid, ibis.Table)

    def test_no_schema_component_passes_through(self):
        """Components with no field definitions pass through unchanged."""
        rows = [{"entity_id": "e1", "component_index": 0, "value": "hello"}]
        components = {"desc": _make_component_table(rows)}
        validated, _ = _call(components, [], [])
        assert "desc" in validated
        df = validated["desc"].execute()
        assert df.iloc[0]["value"] == "hello"

    def test_str_field_coercion(self):
        components = {"mycomp": _make_component_table([
            {"entity_id": "e1", "component_index": 0, "name": "Alice"},
        ])}
        field_rows = [self._field_row("eid_mycomp", "name", field_type="str")]
        entity_id_rows = [self._entity_id_row("eid_mycomp", "mycomp")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["mycomp"].execute()
        assert df.iloc[0]["name"] == "Alice"

    def test_float_field_cast_from_string(self):
        components = {"scores": _make_component_table([
            {"entity_id": "e1", "component_index": 0, "score": "3.14"},
        ])}
        field_rows = [self._field_row("eid_scores", "score", field_type="float")]
        entity_id_rows = [self._entity_id_row("eid_scores", "scores")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["scores"].execute()
        assert abs(df.iloc[0]["score"] - 3.14) < 1e-6

    def test_bool_field_cast_from_string(self):
        components = {"flags": _make_component_table([
            {"entity_id": "e1", "component_index": 0, "active": "True"},
            {"entity_id": "e2", "component_index": 0, "active": "False"},
        ])}
        field_rows = [self._field_row("eid_flags", "active", field_type="bool")]
        entity_id_rows = [self._entity_id_row("eid_flags", "flags")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["flags"].execute().sort_values("entity_id").reset_index(drop=True)
        assert df.iloc[0]["active"] is True or df.iloc[0]["active"] == True
        assert df.iloc[1]["active"] is False or df.iloc[1]["active"] == False

    def test_missing_column_added_as_null(self):
        """A typed column missing from the component table is added as null."""
        components = {"things": _make_component_table([
            {"entity_id": "e1", "component_index": 0},
        ])}
        field_rows = [self._field_row("eid_things", "score", field_type="float")]
        entity_id_rows = [self._entity_id_row("eid_things", "things")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["things"].execute()
        assert "score" in df.columns
        assert pd.isna(df.iloc[0]["score"])

    def test_default_applied_when_null(self):
        """Default values are filled in for null fields."""
        components = {"items": _make_component_table([
            {"entity_id": "e1", "component_index": 0, "priority": None},
        ])}
        field_rows = [self._field_row("eid_items", "priority", field_type="float", default=0.5)]
        entity_id_rows = [self._entity_id_row("eid_items", "items")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["items"].execute()
        assert abs(df.iloc[0]["priority"] - 0.5) < 1e-6

    def test_nullable_violation_collected(self):
        """Null values in non-nullable fields appear in invalid_field."""
        components = {"reqs": _make_component_table([
            {"entity_id": "e1", "component_index": 1, "value": None},
        ])}
        field_rows = [self._field_row("eid_reqs", "value", field_type="float", nullable=False)]
        entity_id_rows = [self._entity_id_row("eid_reqs", "reqs")]
        _, invalid = _call(components, field_rows, entity_id_rows)
        df = invalid.execute()
        assert len(df) == 1
        assert df.iloc[0]["component_type"] == "reqs"
        assert df.iloc[0]["field"] == "value"
        assert df.iloc[0]["error_type"] == "nullable"

    def test_range_violation_collected(self):
        """Values outside a categorical range appear in invalid_field."""
        components = {"food": _make_component_table([
            {"entity_id": "e1", "component_index": 1, "type": "cosmic_horror"},
        ])}
        field_rows = [self._field_row("eid_food", "type", field_type="str", nullable=True, field_range=["wet", "dry"])]
        entity_id_rows = [self._entity_id_row("eid_food", "food")]
        _, invalid = _call(components, field_rows, entity_id_rows)
        df = invalid.execute()
        assert len(df) == 1
        assert df.iloc[0]["error_type"] == "range"
        assert df.iloc[0]["value"] == "cosmic_horror"

    def test_valid_range_produces_no_violation(self):
        """Values within a categorical range produce no violations."""
        components = {"food": _make_component_table([
            {"entity_id": "e1", "component_index": 1, "type": "wet"},
        ])}
        field_rows = [self._field_row("eid_food", "type", field_type="str", nullable=True, field_range=["wet", "dry"])]
        entity_id_rows = [self._entity_id_row("eid_food", "food")]
        _, invalid = _call(components, field_rows, entity_id_rows)
        df = invalid.execute()
        assert len(df) == 0

    def test_no_violations_returns_empty_invalid_field(self):
        """When there are no violations, invalid_field is an empty table with correct schema."""
        components = {"desc": _make_component_table([{"entity_id": "e1", "component_index": 0, "value": "ok"}])}
        _, invalid = _call(components, [], [])
        df = invalid.execute()
        assert df.empty
        assert set(df.columns) >= {"entity_id", "component_index", "component_type", "field", "value", "error_type"}

    def test_all_rows_preserved(self):
        """Validation does not drop any rows from the component table."""
        rows = [
            {"entity_id": f"e{i}", "component_index": i, "name": f"item{i}"}
            for i in range(5)
        ]
        components = {"items": _make_component_table(rows)}
        field_rows = [self._field_row("eid_items", "name", field_type="str")]
        entity_id_rows = [self._entity_id_row("eid_items", "items")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["items"].execute()
        assert len(df) == 5

    def test_multiple_components_validated_independently(self):
        """Each component type uses its own field schema."""
        components = {
            "cats": _make_component_table([{"entity_id": "e1", "component_index": 0, "name": "Felix"}]),
            "dogs": _make_component_table([{"entity_id": "e2", "component_index": 0, "breed": "Poodle"}]),
        }
        field_rows = [
            self._field_row("eid_cats", "name", field_type="str"),
            self._field_row("eid_dogs", "breed", field_type="str"),
        ]
        entity_id_rows = [
            self._entity_id_row("eid_cats", "cats"),
            self._entity_id_row("eid_dogs", "dogs"),
        ]
        validated, invalid = _call(components, field_rows, entity_id_rows)
        assert "cats" in validated
        assert "dogs" in validated
        assert invalid.execute().empty

    def test_empty_string_treated_as_null_for_default(self):
        """Empty strings in str fields are treated as null before applying defaults."""
        components = {"items": _make_component_table([
            {"entity_id": "e1", "component_index": 0, "label": ""},
        ])}
        field_rows = [self._field_row("eid_items", "label", field_type="str", default="unknown")]
        entity_id_rows = [self._entity_id_row("eid_items", "items")]
        validated, _ = _call(components, field_rows, entity_id_rows)
        df = validated["items"].execute()
        assert df.iloc[0]["label"] == "unknown"

    def test_multiple_violations_unioned(self):
        """Multiple violations across fields are all collected in invalid_field."""
        components = {"reqs": _make_component_table([
            {"entity_id": "e1", "component_index": 1, "value": None, "type": "unknown"},
        ])}
        field_rows = [
            self._field_row("eid_reqs", "value", field_type="float", nullable=False),
            self._field_row("eid_reqs", "type", field_type="str", nullable=True, field_range=["functional", "quality"]),
        ]
        entity_id_rows = [self._entity_id_row("eid_reqs", "reqs")]
        _, invalid = _call(components, field_rows, entity_id_rows)
        df = invalid.execute()
        assert len(df) == 2
        assert set(df["error_type"]) == {"nullable", "range"}

    def test_unrecognized_entity_key_ignored(self):
        """Components without matching field definitions are passed through."""
        components = {"orphan": _make_component_table([{"entity_id": "e1", "component_index": 0, "value": "x"}])}
        field_rows = [self._field_row("eid_other", "value", field_type="str")]
        entity_id_rows = [self._entity_id_row("eid_other", "other")]  # "other" != "orphan"
        validated, invalid = _call(components, field_rows, entity_id_rows)
        assert "orphan" in validated
        df = validated["orphan"].execute()
        assert df.iloc[0]["value"] == "x"
        assert invalid.execute().empty


class TestTimeFilledComponents:
    """Tests for time_filled_components, which backfills time_dimension fields."""

    def _entity_id_row(self, entity_id, entity_key):
        return {"value": entity_id, "entity_key": entity_key, "path": f"test:{entity_key}", "alias": entity_key}

    def _field_row(self, entity_id, field_name, time_dimension=None):
        return {
            "entity_id": entity_id,
            "component_index": 0,
            "value": field_name,
            "time_dimension": time_dimension,
        }

    def _status_reading_table(self):
        return _make_component_table([
            {"entity_id": "e1", "component_index": 0, "as_of": None, "status": "open"},
            {"entity_id": "e2", "component_index": 0, "as_of": "2024-01-01", "status": "closed"},
        ])

    def _field_and_entity_id(self):
        field = _make_field_table([
            self._field_row("def1", "as_of", time_dimension="True"),
            self._field_row("def1", "status", time_dimension="False"),
        ])
        entity_id = _make_entity_id_table([self._entity_id_row("def1", "status_reading")])
        return field, entity_id

    def test_no_load_time_is_noop(self):
        components = {"status_reading": self._status_reading_table()}
        field, entity_id = self._field_and_entity_id()
        result = validate_components.time_filled_components(components, field, entity_id, load_time=None)
        assert result is components

    def test_fills_null_time_dimension_values(self):
        components = {"status_reading": self._status_reading_table()}
        field, entity_id = self._field_and_entity_id()
        result = validate_components.time_filled_components(
            components, field, entity_id, load_time="2024-12-25"
        )
        df = result["status_reading"].execute()
        assert df.set_index("entity_id").loc["e1", "as_of"] == "2024-12-25"

    def test_does_not_overwrite_existing_values(self):
        components = {"status_reading": self._status_reading_table()}
        field, entity_id = self._field_and_entity_id()
        result = validate_components.time_filled_components(
            components, field, entity_id, load_time="2024-12-25"
        )
        df = result["status_reading"].execute()
        assert df.set_index("entity_id").loc["e2", "as_of"] == "2024-01-01"

    def test_leaves_non_time_dimension_fields_untouched(self):
        components = {"status_reading": self._status_reading_table()}
        field, entity_id = self._field_and_entity_id()
        result = validate_components.time_filled_components(
            components, field, entity_id, load_time="2024-12-25"
        )
        df = result["status_reading"].execute()
        assert df.set_index("entity_id").loc["e1", "status"] == "open"

    def test_no_time_dimension_column_is_noop(self):
        components = {"status_reading": self._status_reading_table()}
        field = _make_field_table([{"entity_id": "def1", "component_index": 0, "value": "as_of"}])
        entity_id = _make_entity_id_table([self._entity_id_row("def1", "status_reading")])
        result = validate_components.time_filled_components(
            components, field, entity_id, load_time="2024-12-25"
        )
        assert result is components

    def test_multiple_time_dimension_fields_raises(self):
        components = {"status_reading": self._status_reading_table()}
        field = _make_field_table([
            self._field_row("def1", "as_of", time_dimension="True"),
            self._field_row("def1", "also_as_of", time_dimension="True"),
        ])
        entity_id = _make_entity_id_table([self._entity_id_row("def1", "status_reading")])
        with pytest.raises(ValueError, match="status_reading"):
            validate_components.time_filled_components(
                components, field, entity_id, load_time="2024-12-25"
            )
