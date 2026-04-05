import pandas as pd
import pytest

from iacs.utils import candidate_entity_ids


@pytest.fixture
def entity_id_df():
    return pd.DataFrame([
        {"value": "aaa111aaa111", "path": "examples/minimal2/minimal2.yaml:core_requirement.first_subrequirement"},
        {"value": "bbb222bbb222", "path": "examples/minimal2/minimal2.yaml:core_requirement.second_subrequirement"},
        {"value": "ccc333ccc333", "path": "examples/minimal2/minimal2.yaml:core_requirement"},
        {"value": "ddd444ddd444", "path": "examples/minimal2/minimal2.yaml:my_infrastructure"},
    ])


def test_exact_full_path_match(entity_id_df):
    result = candidate_entity_ids(
        "core_requirement.first_subrequirement", entity_id_df
    )
    assert result == ["aaa111aaa111"]


def test_partial_substring_match(entity_id_df):
    result = candidate_entity_ids("first_subrequirement", entity_id_df)
    assert result == ["aaa111aaa111"]


def test_no_match_returns_empty(entity_id_df):
    result = candidate_entity_ids("nonexistent_entity", entity_id_df)
    assert result == []


def test_ambiguous_matches_returns_multiple(entity_id_df):
    result = candidate_entity_ids("subrequirement", entity_id_df)
    assert set(result) == {"aaa111aaa111", "bbb222bbb222"}
