"""Tests for the validate_registry Hamilton DAG functions."""

import ibis
import pandas as pd
import pytest

import iacs.dataflows.validate_registry as validate_registry
from iacs.utils import dhash


# The entity_id for data_structure.field in builtins
_FIELD_ENTITY_ID = dhash("builtins.components:data_structure.field")


def _make_field_table(rows: list[dict]) -> ibis.Table:
    """Build a field component ibis table from a list of row dicts."""
    return ibis.memtable(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# validated_field
# ---------------------------------------------------------------------------

class TestValidatedField:

    def _schema_rows(self, extra: dict | None = None) -> list[dict]:
        """Build the canonical field-of-field rows from data_structure.field."""
        base = [
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 0, "value": "value",       "type": "str"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 1, "value": "description",  "type": "str"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 2, "value": "type",          "type": "str"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 3, "value": "nullable",      "type": "bool"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 4, "value": "unique",        "type": "bool"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 5, "value": "default"},
            {"entity_id": _FIELD_ENTITY_ID, "component_index": 6, "value": "range"},
        ]
        if extra:
            base.append(extra)
        return base

    def _execute(self, result) -> pd.DataFrame:
        """Materialise the lazy ibis result returned by validated_field."""
        return result.execute()

    def test_returns_ibis_table(self):
        rows = self._schema_rows()
        field = _make_field_table(rows)
        result = validate_registry.validated_field(field)
        assert isinstance(result, ibis.Table)

    def test_bool_field_coerced_from_true_string(self):
        rows = self._schema_rows() + [
            {"entity_id": "abc123", "component_index": 0, "value": "my_field",
             "nullable": "True", "unique": "False"},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        data_row = df[df["entity_id"] == "abc123"].iloc[0]
        assert data_row["nullable"] is True
        assert data_row["unique"] is False

    def test_bool_field_coerced_from_false_string(self):
        rows = self._schema_rows() + [
            {"entity_id": "def456", "component_index": 0, "value": "x",
             "nullable": "False", "unique": "True"},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        data_row = df[df["entity_id"] == "def456"].iloc[0]
        assert data_row["nullable"] is False
        assert data_row["unique"] is True

    def test_bool_field_empty_string_becomes_none(self):
        rows = self._schema_rows() + [
            {"entity_id": "ghi789", "component_index": 0, "value": "y",
             "nullable": "", "unique": ""},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        data_row = df[df["entity_id"] == "ghi789"].iloc[0]
        assert data_row["nullable"] is None or pd.isna(data_row["nullable"])
        assert data_row["unique"] is None or pd.isna(data_row["unique"])

    def test_str_fields_unchanged(self):
        rows = self._schema_rows() + [
            {"entity_id": "jkl012", "component_index": 0,
             "value": "my_col", "description": "A column.", "type": "str"},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        data_row = df[df["entity_id"] == "jkl012"].iloc[0]
        assert data_row["value"] == "my_col"
        assert data_row["description"] == "A column."
        assert data_row["type"] == "str"

    def test_untyped_fields_left_as_is(self):
        """Fields without a type constraint (default, range) are not coerced."""
        rows = self._schema_rows() + [
            {"entity_id": "mno345", "component_index": 0, "value": "z",
             "default": "42", "range": "[0, 100]"},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        data_row = df[df["entity_id"] == "mno345"].iloc[0]
        assert data_row["default"] == "42"
        assert data_row["range"] == "[0, 100]"

    def test_all_rows_preserved(self):
        """No rows are dropped during validation."""
        rows = self._schema_rows() + [
            {"entity_id": "aaa", "component_index": 0, "value": "a"},
            {"entity_id": "bbb", "component_index": 0, "value": "b"},
        ]
        field = _make_field_table(rows)
        df = self._execute(validate_registry.validated_field(field))
        assert len(df) == len(rows)
