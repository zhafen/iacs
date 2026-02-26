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


# ---------------------------------------------------------------------------
# derived_field
# ---------------------------------------------------------------------------

def _field_row(entity_id, field_name, field_type=None, component_index=0):
    return {"entity_id": entity_id, "component_index": component_index,
            "value": field_name, "type": field_type}


def _parent_row(entity_id, parent_id):
    return {"entity_id": entity_id, "parent_id": parent_id}


def _empty_parent():
    return ibis.memtable(pd.DataFrame([], columns=["entity_id", "parent_id"]))


class TestDerivedField:

    def _call(self, field_rows, parent_rows=None):
        field = ibis.memtable(pd.DataFrame(field_rows))
        parent = (
            _empty_parent() if not parent_rows
            else ibis.memtable(pd.DataFrame(parent_rows))
        )
        return validate_registry.derived_field(field, parent).execute()

    def _field_names(self, df, entity_id):
        return set(df[df["entity_id"] == entity_id]["value"])

    def test_returns_ibis_table(self):
        field = ibis.memtable(pd.DataFrame([_field_row("e1", "x", "str")]))
        result = validate_registry.derived_field(field, _empty_parent())
        assert isinstance(result, ibis.Table)

    def test_entity_with_no_parent_has_own_fields(self):
        df = self._call([_field_row("e1", "x"), _field_row("e1", "y", component_index=1)])
        assert self._field_names(df, "e1") == {"x", "y"}

    def test_child_inherits_parent_fields(self):
        df = self._call(
            [_field_row("parent", "x"), _field_row("child", "y")],
            [_parent_row("child", "parent")],
        )
        assert "x" in self._field_names(df, "child")
        assert "y" in self._field_names(df, "child")

    def test_parent_is_not_affected_by_child(self):
        df = self._call(
            [_field_row("parent", "x"), _field_row("child", "y")],
            [_parent_row("child", "parent")],
        )
        assert self._field_names(df, "parent") == {"x"}

    def test_child_overrides_parent_field(self):
        df = self._call(
            [_field_row("parent", "x", "str"), _field_row("child", "x", "bool")],
            [_parent_row("child", "parent")],
        )
        row = df[(df["entity_id"] == "child") & (df["value"] == "x")]
        assert len(row) == 1
        assert row.iloc[0]["type"] == "bool"

    def test_multi_level_inheritance(self):
        df = self._call(
            [_field_row("gp", "a"), _field_row("p", "b"), _field_row("c", "c_field")],
            [_parent_row("p", "gp"), _parent_row("c", "p")],
        )
        assert self._field_names(df, "c") == {"a", "b", "c_field"}

    def test_entity_with_no_own_fields_inherits_all_parent_fields(self):
        df = self._call(
            [_field_row("parent", "x"), _field_row("parent", "y", component_index=1)],
            [_parent_row("child", "parent")],
        )
        assert self._field_names(df, "child") == {"x", "y"}

    def test_no_duplicate_field_names_per_entity(self):
        df = self._call(
            [_field_row("parent", "x"), _field_row("child", "y")],
            [_parent_row("child", "parent")],
        )
        child_rows = df[df["entity_id"] == "child"]
        assert len(child_rows) == child_rows["value"].nunique()

    def test_cycle_in_parent_hierarchy_does_not_hang(self):
        """A cycle in parent links should not cause infinite loops."""
        df = self._call(
            [_field_row("a", "x")],
            [_parent_row("a", "b"), _parent_row("b", "a")],
        )
        assert "x" in self._field_names(df, "a")
