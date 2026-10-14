"""Tests for the audit.requirement_coverage dataflow."""

from emc2p.registry import Registry
from iacs.registrar import Registrar


def test_relation_only_requirement_is_covered_without_requirement_priority():
    """An entity needs no `requirement_priority` tag to show up in the
    coverage audit -- being solved by a `solution` relation is enough, per
    the relation-only requirement/solution convention documented on those
    component types in emc2p's builtins/auditing.yaml. This is the
    convention a plain requirement/candidate-solutions pairing should use
    instead of `requirement_priority`.
    """
    registrar = Registrar(
        Registry.from_component_rows({
            "entity_id": [
                {"value": "untagged_req"},
                {"value": "candidate_solution"},
            ],
            # value_eid is normally populated by derive_components from the
            # entity_ref-typed "value" field; set it directly here since
            # Registry.from_component_rows bypasses that resolution step.
            "solution": [
                {"entity_id": "candidate_solution", "value": "untagged_req", "value_eid": "untagged_req"},
            ],
        })
    )
    result = registrar.execute("audit.requirement_coverage")
    coverage = result["requirement_coverage"].execute()

    assert "untagged_req" in set(coverage["entity_id"])
    row = coverage[coverage["entity_id"] == "untagged_req"].iloc[0]
    assert row["solution_eid"] == "candidate_solution"


def test_requirement_relation_entities_are_covered_without_requirement_priority():
    """Mirrors the `requirement` half of the relation-only convention (the
    `solution` half is covered above): an entity identified only by being
    either side of a `requirement` relation -- e.g.
    null_value_representation in iacs.yaml, identified only by
    `requirement of` -- must still show up here with no solution, rather
    than being silently dropped because it has no `requirement_priority`
    tag and nothing `solution`s it directly.
    """
    registrar = Registrar(
        Registry.from_component_rows({
            "entity_id": [
                {"value": "needed_thing"},
                {"value": "needer_thing"},
            ],
            # value_eid is normally populated by derive_components from the
            # entity_ref-typed "value" field; set it directly here since
            # Registry.from_component_rows bypasses that resolution step.
            "requirement": [
                {"entity_id": "needed_thing", "value": "needer_thing", "value_eid": "needer_thing"},
            ],
        })
    )
    result = registrar.execute("audit.requirement_coverage")
    coverage = result["requirement_coverage"].execute()

    covered_ids = set(coverage["entity_id"])
    assert "needed_thing" in covered_ids
    assert "needer_thing" in covered_ids
