"""Tests for the audit.traceability dataflow."""

import pytest

from emc2p.registry import Registry
from iacs.registrar import Registrar


def _registrar_with_orphans():
    """A registry with one genuine untraced entity and one todo-only entity.

    `req1`/`sol1` is a `requirement_priority`-tagged requirement with a
    solution. `req2`/`sol2` is the relation-only convention instead: `req2`
    carries no `requirement_priority` tag at all and is recognized purely
    as the target (`value_eid`) of `sol2`'s `solution` relation (see
    emc2p's builtins/auditing.yaml). `real_orphan` has none of
    `requirement_priority`, `solution`, or `todo` -- a real gap in
    traceability. `todo_only` has no `requirement_priority`/`solution`
    either, but does carry a `todo` -- a tracked, intentional pending item,
    not an unvalidated solution. `traceability` doesn't read `todo` at all
    (see INPUT_COMPONENT_TYPES in iacs/dataflows/audit/traceability.py), so
    both currently land in the same orphan bucket.
    """
    return Registry.from_component_rows({
        "entity_id": [
            {"value": "req1"},
            {"value": "sol1"},
            {"value": "req2"},
            {"value": "sol2"},
            {"value": "todo_only"},
            {"value": "real_orphan"},
        ],
        "requirement_priority": [
            {"entity_id": "req1", "value": "Something the system must do."},
        ],
        # value_eid is normally populated by derive_components from the
        # entity_ref-typed "value" field; set it directly here since
        # Registry.from_component_rows bypasses that resolution step.
        "solution": [
            {"entity_id": "sol1", "value": "req1", "value_eid": "req1"},
            {"entity_id": "sol2", "value": "req2", "value_eid": "req2"},
        ],
        "todo": [
            {"entity_id": "todo_only", "value": "Something to follow up on later."},
        ],
    })


def test_solution_entities_and_their_relation_only_requirements_are_not_orphans():
    """Regression test for a real bug: the dataflow used to fetch the
    `solution` component under the stale key `"solution of"`, which is
    always empty in a real registry (the canonical, loaded component type
    is `solution`) -- so every solution entity was wrongly flagged as an
    untraced orphan. Also covers the relation-only requirement convention:
    `req2` has no `requirement_priority` tag and must still be recognized
    as a requirement purely by being `sol2`'s solution target."""
    a = Registrar(_registrar_with_orphans())
    result = a.execute("audit.traceability")
    orphan_ids = set(result["traceability"].execute()["entity_id"])

    assert "real_orphan" in orphan_ids
    assert orphan_ids.isdisjoint({"req1", "sol1", "req2", "sol2"})


@pytest.mark.skip(
    reason=(
        "Documents a known gap (PR#96 review comment 3 / task #26), not yet fixed: "
        "the traceability audit doesn't have its own concept of 'unvalidated solution' "
        "-- it flags anything lacking both `requirement_priority` and `solution of` as a generic "
        "orphan, so a todo-only entity (tracked, intentional pending work) gets the same "
        "'does not trace to any requirement' message as a genuinely untraced entity. "
        "Un-skip this once the audit is reworked to tell those apart."
    )
)
def test_todo_only_entity_is_not_flagged_as_an_untraced_orphan():
    a = Registrar(_registrar_with_orphans())
    result = a.execute("audit.traceability")
    orphan_ids = set(result["traceability"].execute()["entity_id"])

    assert "real_orphan" in orphan_ids, "a genuinely untraced entity should still be flagged"
    assert "todo_only" not in orphan_ids, (
        "a todo-only entity is tracked, intentional pending work, not an unvalidated "
        "solution -- it shouldn't be indistinguishable from a real orphan"
    )
