"""Tests for iacs.views.requirement_tree."""

from tests.conftest import make_registry
from iacs.views.requirement_tree import build_requirement_forest, build_requirement_tree


def _registry(entity_id_rows, parent_rows, requirement_rows):
    # make_registry/duckdb can't create a table from an empty row list (no
    # columns to infer), so omitted component types fall back to Registry's
    # generic empty entity_id/value schema instead.
    components = {"entity_id": entity_id_rows}
    if parent_rows:
        components["parent"] = parent_rows
    if requirement_rows:
        components["requirement"] = requirement_rows
    return make_registry(components)


class TestBuildRequirementForest:

    def test_no_requirements_returns_empty_root(self):
        registry = _registry(
            entity_id_rows=[{"value": "e1", "entity_key": "e1"}],
            parent_rows=[],
            requirement_rows=[],
        )
        forest = build_requirement_forest(registry)
        assert forest == {"name": "Requirements", "priority": None}

    def test_single_root_returned_directly(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "root", "entity_key": "root_req"},
                {"value": "child", "entity_key": "child_req"},
            ],
            parent_rows=[{"entity_id": "child", "parent_eid": "root"}],
            requirement_rows=[
                {"entity_id": "root", "value": 1.0},
                {"entity_id": "child", "value": 0.5},
            ],
        )
        forest = build_requirement_forest(registry)
        assert forest["name"] == "root_req"
        assert forest["priority"] == 1.0
        assert len(forest["children"]) == 1
        assert forest["children"][0]["name"] == "child_req"

    def test_multiple_roots_wrapped_and_sorted_by_priority(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "low", "entity_key": "low_priority_req"},
                {"value": "high", "entity_key": "high_priority_req"},
            ],
            parent_rows=[],
            requirement_rows=[
                {"entity_id": "low", "value": 0.2},
                {"entity_id": "high", "value": 0.9},
            ],
        )
        forest = build_requirement_forest(registry)
        assert forest["name"] == "Requirements"
        assert forest["priority"] is None
        names = [c["name"] for c in forest["children"]]
        assert names == ["high_priority_req", "low_priority_req"]

    def test_non_requirement_intermediate_entity_is_not_a_new_root(self):
        """A requirement nested behind a non-requirement entity is still
        recognized as having a requirement ancestor (so it isn't promoted to
        a root), even though — matching build_requirement_tree's existing
        direct-adjacency assumption — children_map only links directly
        connected requirement entities, so it doesn't surface as a child
        either."""
        registry = _registry(
            entity_id_rows=[
                {"value": "root", "entity_key": "root_req"},
                {"value": "mid", "entity_key": "non_requirement_entity"},
                {"value": "leaf", "entity_key": "leaf_req"},
            ],
            parent_rows=[
                {"entity_id": "mid", "parent_eid": "root"},
                {"entity_id": "leaf", "parent_eid": "mid"},
            ],
            requirement_rows=[
                {"entity_id": "root", "value": 1.0},
                {"entity_id": "leaf", "value": 0.5},
            ],
        )
        forest = build_requirement_forest(registry)
        assert forest["name"] == "root_req"
        assert "children" not in forest


class TestBuildRequirementTreeUnchanged:
    """Regression guard: build_requirement_tree keeps its original ancestor-scoped behavior."""

    def test_builds_tree_from_ancestor_key(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "root", "entity_key": "root_req"},
                {"value": "child", "entity_key": "child_req"},
            ],
            parent_rows=[{"entity_id": "child", "parent_eid": "root"}],
            requirement_rows=[
                {"entity_id": "root", "value": 1.0},
                {"entity_id": "child", "value": 0.5},
            ],
        )
        tree = build_requirement_tree(registry, "root_req")
        assert tree == {
            "name": "root_req",
            "priority": 1.0,
            "children": [{"name": "child_req", "priority": 0.5}],
        }

    def test_raises_for_unknown_ancestor_key(self):
        registry = _registry(
            entity_id_rows=[{"value": "e1", "entity_key": "e1"}],
            parent_rows=[],
            requirement_rows=[],
        )
        try:
            build_requirement_tree(registry, "does_not_exist")
        except ValueError as e:
            assert "does_not_exist" in str(e)
        else:
            raise AssertionError("Expected ValueError")
