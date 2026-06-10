"""Tests for the strip_description_whitespace Hamilton DAG functions."""

import ibis
import pandas as pd

import iacs.dataflows.derive.strip_description_whitespace as sut
from tests.conftest import make_registry


def _field_table(rows):
    return ibis.memtable(pd.DataFrame(rows, columns=["entity_id", "value", "type"]))


def _entity_id_table(rows):
    return ibis.memtable(pd.DataFrame(rows, columns=["value", "entity_key"]))


class TestFieldsOfTypeDescription:

    def test_returns_empty_when_no_description_fields(self):
        field = _field_table([{"entity_id": "e1", "value": "foo", "type": "str"}])
        entity_id = _entity_id_table([{"value": "e1", "entity_key": "mycomp"}])
        result = sut.fields_of_type_description(field, entity_id)
        assert result == {}

    def test_returns_field_for_description_type(self):
        field = _field_table([{"entity_id": "e1", "value": "summary", "type": "description"}])
        entity_id = _entity_id_table([{"value": "e1", "entity_key": "mycomp"}])
        result = sut.fields_of_type_description(field, entity_id)
        assert result == {"mycomp": ["summary"]}

    def test_multiple_fields_same_component(self):
        field = _field_table([
            {"entity_id": "e1", "value": "a", "type": "description"},
            {"entity_id": "e1", "value": "b", "type": "description"},
        ])
        entity_id = _entity_id_table([{"value": "e1", "entity_key": "comp"}])
        result = sut.fields_of_type_description(field, entity_id)
        assert set(result["comp"]) == {"a", "b"}

    def test_skips_entity_id_not_in_entity_id_table(self):
        field = _field_table([{"entity_id": "unknown", "value": "x", "type": "description"}])
        entity_id = _entity_id_table([{"value": "e1", "entity_key": "comp"}])
        result = sut.fields_of_type_description(field, entity_id)
        assert result == {}


class TestStrippedRegistry:

    def test_strips_description_value_column(self):
        reg = make_registry({
            "description": [
                {"entity_id": "e1", "value": "  hello world  \n"},
                {"entity_id": "e2", "value": "\ttabbed\t"},
            ],
        })
        result = sut.stripped_registry(reg, {})
        df = result._components["description"].to_pandas()
        assert df.loc[df["entity_id"] == "e1", "value"].iloc[0] == "hello world"
        assert df.loc[df["entity_id"] == "e2", "value"].iloc[0] == "tabbed"

    def test_no_description_component_does_not_error(self):
        from iacs.registry import Registry
        reg = make_registry({})
        result = sut.stripped_registry(reg, {})
        assert isinstance(result, Registry)

    def test_strips_fields_of_type_description_in_other_components(self):
        reg = make_registry({
            "mycomp": [
                {"entity_id": "e1", "summary": "  padded  ", "other": "  untouched  "},
            ],
        })
        result = sut.stripped_registry(reg, {"mycomp": ["summary"]})
        df = result._components["mycomp"].to_pandas()
        assert df.loc[0, "summary"] == "padded"
        assert df.loc[0, "other"] == "  untouched  "

    def test_non_string_values_are_unchanged(self):
        reg = make_registry({
            "description": [
                {"entity_id": "e1", "value": "  text  "},
                {"entity_id": "e2", "value": None},
            ],
        })
        result = sut.stripped_registry(reg, {})
        df = result._components["description"].to_pandas()
        assert df.loc[df["entity_id"] == "e1", "value"].iloc[0] == "text"
        assert pd.isna(df.loc[df["entity_id"] == "e2", "value"].iloc[0])
