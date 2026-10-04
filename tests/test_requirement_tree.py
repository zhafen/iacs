"""Tests for iacs.views.requirement_tree."""

from emc2p.registry import Registry
from iacs.views.requirement_tree import build_requirement_forest, build_requirement_tree


def _registry(entity_id_rows, parent_rows, requirement_rows, solution_rows=None):
    # Registry.from_component_rows/duckdb can't create a table from an empty
    # row list (no columns to infer), so omitted component types fall back
    # to Registry's generic empty entity_id/value schema instead.
    components = {"entity_id": entity_id_rows}
    if parent_rows:
        components["parent"] = parent_rows
    if requirement_rows:
        components["requirement_priority"] = requirement_rows
    if solution_rows:
        # value_eid is normally populated by derive_components from the
        # entity_ref-typed "value" field; these raw rows set it directly
        # since this helper builds the registry from component rows rather
        # than running the full load pipeline.
        components["solution"] = solution_rows
    return Registry.from_component_rows(components)


class TestBuildRequirementForest:

    def test_no_requirements_returns_empty_root(self):
        registry = _registry(
            entity_id_rows=[{"value": "e1", "display_key": "e1"}],
            parent_rows=[],
            requirement_rows=[],
        )
        forest = build_requirement_forest(registry)
        assert forest == {"name": "Requirements", "priority": None}

    def test_single_root_returned_directly(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "root", "display_key": "root_req"},
                {"value": "child", "display_key": "child_req"},
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
                {"value": "low", "display_key": "low_priority_req"},
                {"value": "high", "display_key": "high_priority_req"},
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
                {"value": "root", "display_key": "root_req"},
                {"value": "mid", "display_key": "non_requirement_entity"},
                {"value": "leaf", "display_key": "leaf_req"},
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

    def test_solution_target_without_requirement_priority_is_a_requirement(self):
        """An entity needs no `requirement_priority` tag to be treated as a
        requirement -- being solved by a `solution` relation is enough, per
        the relation-only requirement/solution convention documented on
        those component types in emc2p's builtins/auditing.yaml. Its
        priority is reported as None (never defaulted to 0.5) so a view
        can distinguish it from a `requirement_priority`-scored node."""
        registry = _registry(
            entity_id_rows=[
                {"value": "untagged_req", "display_key": "untagged_req"},
                {"value": "candidate_solution", "display_key": "candidate_solution"},
            ],
            parent_rows=[],
            requirement_rows=[],
            solution_rows=[
                {"entity_id": "candidate_solution", "value": "untagged_req", "value_eid": "untagged_req"},
            ],
        )
        forest = build_requirement_forest(registry)
        assert forest["name"] == "untagged_req"
        assert forest["priority"] is None
        assert "children" not in forest

    def test_tagged_and_relation_only_requirements_both_appear_as_roots(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "scored", "display_key": "scored_req"},
                {"value": "unscored", "display_key": "unscored_req"},
                {"value": "sol", "display_key": "sol"},
            ],
            parent_rows=[],
            requirement_rows=[{"entity_id": "scored", "value": 0.5}],
            solution_rows=[
                {"entity_id": "sol", "value": "unscored", "value_eid": "unscored"},
            ],
        )
        forest = build_requirement_forest(registry)
        names = {c["name"]: c["priority"] for c in forest["children"]}
        assert names == {"scored_req": 0.5, "unscored_req": None}


class TestBuildRequirementTreeUnchanged:
    """Regression guard: build_requirement_tree keeps its original ancestor-scoped behavior."""

    def test_builds_tree_from_ancestor_key(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "root", "display_key": "root_req"},
                {"value": "child", "display_key": "child_req"},
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
            entity_id_rows=[{"value": "e1", "display_key": "e1"}],
            parent_rows=[],
            requirement_rows=[],
        )
        try:
            build_requirement_tree(registry, "does_not_exist")
        except ValueError as e:
            assert "does_not_exist" in str(e)
        else:
            raise AssertionError("Expected ValueError")
