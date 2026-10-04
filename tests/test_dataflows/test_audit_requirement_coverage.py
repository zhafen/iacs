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
