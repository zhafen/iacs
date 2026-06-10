"""Tests for alternate YAML format conversion."""

import pytest

from iacs.alternate_yaml import (
    entity_first_to_alternate,
    alternate_to_entity_first,
)
import iacs.dataflows.etl.load_manifest as load_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ef(entity_first_dict: dict) -> dict:
    """Wrap a per-entity dict so it looks like a single-file entity_first_data."""
    return entity_first_dict


def _pathvalue_from_ef(ef_data: dict) -> list[tuple[str, str]]:
    """Run _flatten_to_pathvalue on entity-first data keyed by a dummy file id."""
    return load_manifest._flatten_to_pathvalue(ef_data)


# ---------------------------------------------------------------------------
# entity_first_to_alternate — unit tests
# ---------------------------------------------------------------------------

class TestEntityFirstToAlternate:

    def test_tag_component(self):
        ef = {"e": ["requirement"]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"requirement": None}}

    def test_scalar_component(self):
        ef = {"e": [{"description": "hello"}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"description": "hello"}}

    def test_numeric_scalar(self):
        ef = {"e": [{"requirement": 0.9}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"requirement": 0.9}}

    def test_keyed_modifier(self):
        ef = {"e": [{"solution of": "some_req"}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"solution of": "some_req"}}

    def test_multi_instance_list(self):
        ef = {"e": [{"effort": [8, {"value": 2, "schedule": "weekly"}]}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"effort": [8, {"value": 2, "schedule": "weekly"}]}}

    def test_single_subfield_instance(self):
        ef = {"e": [{"link": {"source": "A", "target": "B"}}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"link": [{"source": "A", "target": "B"}]}}

    def test_keyed_multiinstance_field(self):
        ef = {
            "e": [
                {
                    "field": {
                        "name": {"description": "The name.", "type": "str"},
                        "breed": {"description": "The breed.", "type": "str"},
                    }
                }
            ]
        }
        alt = entity_first_to_alternate(ef)
        assert alt == {
            "e": {
                "field": [
                    {"value": "name", "description": "The name.", "type": "str"},
                    {"value": "breed", "description": "The breed.", "type": "str"},
                ]
            }
        }

    def test_nested_entity_with_data(self):
        ef = {
            "parent": {
                "data": [{"description": "top-level desc"}],
                "child": [{"description": "child desc"}],
            }
        }
        alt = entity_first_to_alternate(ef)
        assert alt == {
            "parent": {
                "description": "top-level desc",
                "child": {"description": "child desc"},
            }
        }

    def test_nested_entity_no_own_components(self):
        ef = {"parent": {"child": [{"description": "child desc"}]}}
        alt = entity_first_to_alternate(ef)
        assert alt == {"parent": {"child": {"description": "child desc"}}}

    def test_flat_entity_multiple_components(self):
        ef = {"e": [{"description": "text"}, "requirement", {"alias": "e_alias"}]}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {"description": "text", "requirement": None, "alias": "e_alias"}}

    def test_null_entity_value(self):
        ef = {"e": None}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {}}

    def test_empty_entity_list(self):
        ef = {"e": []}
        alt = entity_first_to_alternate(ef)
        assert alt == {"e": {}}


# ---------------------------------------------------------------------------
# alternate_to_entity_first — unit tests
# ---------------------------------------------------------------------------

class TestAlternateToEntityFirst:

    def test_tag_component(self):
        alt = {"e": {"requirement": None}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": ["requirement"]}

    def test_scalar_component(self):
        alt = {"e": {"description": "hello"}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": [{"description": "hello"}]}

    def test_numeric_scalar(self):
        alt = {"e": {"requirement": 0.9}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": [{"requirement": 0.9}]}

    def test_keyed_modifier(self):
        alt = {"e": {"solution of": "some_req"}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": [{"solution of": "some_req"}]}

    def test_multi_instance_list(self):
        alt = {"e": {"effort": [8, {"value": 2, "schedule": "weekly"}]}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": [{"effort": [8, {"value": 2, "schedule": "weekly"}]}]}

    def test_single_subfield_list(self):
        alt = {"e": {"link": [{"source": "A", "target": "B"}]}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": [{"link": {"source": "A", "target": "B"}}]}

    def test_child_entity(self):
        alt = {"parent": {"child": {"description": "child desc"}}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"parent": {"child": [{"description": "child desc"}]}}

    def test_mixed_components_and_children(self):
        alt = {
            "parent": {
                "description": "parent desc",
                "child": {"description": "child desc"},
            }
        }
        ef = alternate_to_entity_first(alt)
        assert ef == {
            "parent": {
                "data": [{"description": "parent desc"}],
                "child": [{"description": "child desc"}],
            }
        }

    def test_empty_entity(self):
        alt = {"e": {}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"e": []}

    def test_children_only(self):
        alt = {"parent": {"child1": {}, "child2": {"x": 1}}}
        ef = alternate_to_entity_first(alt)
        assert ef == {"parent": {"child1": [], "child2": [{"x": 1}]}}


# ---------------------------------------------------------------------------
# Round-trip tests: entity_first → alternate → entity_first
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def _roundtrip(self, ef_data: dict) -> dict:
        alt = entity_first_to_alternate(ef_data)
        return alternate_to_entity_first(alt)

    def _check_same_pathvalues(self, ef_original: dict, ef_roundtrip: dict):
        """Assert both produce the same (path, value) pairs through the pipeline."""
        pairs_orig = set(_pathvalue_from_ef(ef_original))
        pairs_rt = set(_pathvalue_from_ef(ef_roundtrip))
        assert pairs_orig == pairs_rt, (
            f"Path-value pairs differ.\n"
            f"  Original only: {pairs_orig - pairs_rt}\n"
            f"  Roundtrip only: {pairs_rt - pairs_orig}"
        )

    def test_flat_entity_with_tag(self):
        ef = {"e": ["requirement", {"description": "text"}]}
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_flat_entity_multi_instance(self):
        ef = {"e": [{"effort": [8, {"value": 2, "schedule": "weekly"}]}]}
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_nested_entity(self):
        ef = {
            "parent": {
                "data": [{"description": "top"}, "requirement"],
                "child": [{"description": "child"}, {"alias": "c"}],
            }
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_subfield_component(self):
        ef = {"e": [{"link": {"source": "A", "target": "B", "link_type": "alpha"}}]}
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_keyed_multiinstance_field(self):
        ef = {
            "e": [
                {
                    "field": {
                        "name": {"description": "The name.", "type": "str"},
                        "breed": {"type": "str"},
                    }
                }
            ]
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_minimal_yaml_entities(self):
        ef = {
            "my_requirement": [
                {"description": "A task I need to complete."},
                "requirement",
                {"solution": "my_infrastructure"},
            ],
            "my_infrastructure": [{"description": "Infrastructure to complete the task."}],
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_minimal2_yaml_entities(self):
        ef = {
            "core_requirement": {
                "data": [{"description": "The main requirement."}, "requirement"],
                "first_subrequirement": [{"description": "Sub 1."}, "requirement"],
                "second_subrequirement": [{"description": "Sub 2."}, "requirement"],
            },
            "my_infrastructure": {
                "data": [{"description": "Overall infra."}],
                "infrastructure_for_first_requirement": [
                    {"description": "Solves first."},
                    {"solution of": "core_requirement.first_subrequirement"},
                ],
                "infrastructure_for_second_requirement": [
                    {"description": "Solves second."},
                    {"solution of": "second_subrequirement"},
                ],
            },
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_example_manifest_entities(self):
        """Test key entities from example/manifest.yaml round-trip correctly."""
        ef = {
            "make_cats_happy": {
                "data": [{"description": "The mission."}, {"requirement": 1}],
                "feed_and_water_cats": {
                    "data": [{"description": "Obviously."}, {"requirement": 1}],
                    "feed_cats": [{"requirement": 0.9}, {"alias": "feed_cats"}],
                    "water_cats": ["requirement", {"alias": "water_cats"}],
                },
            },
            "cat_happiness_device": {
                "data": [
                    {"description": "An all-in-one tool."},
                    {"solution of": "make_cats_happy"},
                    "system",
                ],
                "feeding_system": {
                    "data": [
                        {"description": "The feeding system."},
                        {"solution of": "make_cats_happy.feed_and_water_cats"},
                        {"effort": 2},
                    ],
                    "feed_cats": [
                        {"description": "Feed the cats."},
                        {"parent": "task"},
                        {"solution of": "make_cats_happy.feed_and_water_cats.feed_cats"},
                        {"status": "in progress"},
                        {"effort": [8, {"value": 2, "schedule": "weekly"}]},
                    ],
                },
            },
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)

    def test_cat_entity_with_keyed_field(self):
        ef = {
            "cat": [
                {"description": "A data representation of a cat."},
                {
                    "field": {
                        "name": {
                            "description": "The cat's name.",
                            "type": "str",
                            "unique": True,
                        },
                        "breed": {
                            "description": "The breed of the cat.",
                            "type": "str",
                        },
                    }
                },
            ]
        }
        rt = self._roundtrip(ef)
        self._check_same_pathvalues(ef, rt)


# ---------------------------------------------------------------------------
# Full pipeline round-trip: alternate YAML → load → same registry
# ---------------------------------------------------------------------------

class TestFullPipelineRoundTrip:
    """Parse alternate-format YAML through the load_manifest pipeline and
    compare the resulting path-value pairs with those from the original format.
    """

    def _ef_from_alt_yaml_text(self, yaml_text: str) -> dict:
        import yaml as _yaml
        from iacs.alternate_yaml import alternate_to_entity_first
        alt_data = _yaml.safe_load(yaml_text) or {}
        return alternate_to_entity_first(alt_data)

    def _ef_from_yaml_text(self, yaml_text: str) -> dict:
        import yaml as _yaml
        return _yaml.safe_load(yaml_text) or {}

    def _pvpairs(self, ef_data: dict) -> set:
        return set(_pathvalue_from_ef(ef_data))

    def test_minimal_alternate_equals_classic(self):
        classic_yaml = (
            "my_requirement:\n"
            "- description: A task I need to complete.\n"
            "- requirement\n"
            "- solution: my_infrastructure\n"
            "\n"
            "my_infrastructure:\n"
            "- description: Infrastructure to complete the task.\n"
        )
        alternate_yaml = (
            "my_requirement:\n"
            "    description: A task I need to complete.\n"
            "    requirement: ~\n"
            "    solution: my_infrastructure\n"
            "\n"
            "my_infrastructure:\n"
            "    description: Infrastructure to complete the task.\n"
        )
        ef_classic = self._ef_from_yaml_text(classic_yaml)
        ef_alt = self._ef_from_alt_yaml_text(alternate_yaml)
        assert self._pvpairs(ef_classic) == self._pvpairs(ef_alt)

    def test_nested_alternate_equals_classic(self):
        classic_yaml = (
            "parent:\n"
            "    data:\n"
            "        - description: Parent description.\n"
            "        - requirement\n"
            "    child:\n"
            "        - description: Child description.\n"
            "        - solution of: parent\n"
        )
        alternate_yaml = (
            "parent:\n"
            "    description: Parent description.\n"
            "    requirement: ~\n"
            "    child:\n"
            "        description: Child description.\n"
            "        solution of: parent\n"
        )
        ef_classic = self._ef_from_yaml_text(classic_yaml)
        ef_alt = self._ef_from_alt_yaml_text(alternate_yaml)
        assert self._pvpairs(ef_classic) == self._pvpairs(ef_alt)

    def test_multiinstance_effort_equals_classic(self):
        classic_yaml = (
            "task:\n"
            "    - description: A task.\n"
            "    - effort:\n"
            "        - 8\n"
            "        - value: 2\n"
            "          schedule: weekly\n"
        )
        alternate_yaml = (
            "task:\n"
            "    description: A task.\n"
            "    effort:\n"
            "        - 8\n"
            "        - value: 2\n"
            "          schedule: weekly\n"
        )
        ef_classic = self._ef_from_yaml_text(classic_yaml)
        ef_alt = self._ef_from_alt_yaml_text(alternate_yaml)
        assert self._pvpairs(ef_classic) == self._pvpairs(ef_alt)
