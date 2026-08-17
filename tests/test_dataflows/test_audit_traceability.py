"""Tests for the audit.traceability dataflow."""

import pytest

from iacs.registrar import Registrar
from tests.conftest import make_registry


def _registrar_with_orphans():
    """A registry with one genuine untraced entity and one todo-only entity.

    `real_orphan` has no `requirement`, no `solution of`, and no `todo` --
    a real gap in traceability. `todo_only` has no `requirement`/`solution
    of` either, but does carry a `todo` -- a tracked, intentional pending
    item, not an unvalidated solution. `traceability` doesn't read `todo`
    at all (see INPUT_COMPONENT_TYPES in iacs/dataflows/audit/
    traceability.py), so both currently land in the same orphan bucket.
    """
    return make_registry({
        "entity_id": [
            {"value": "req1"},
            {"value": "sol1"},
            {"value": "todo_only"},
            {"value": "real_orphan"},
        ],
        "requirement": [
            {"entity_id": "req1", "value": "Something the system must do."},
        ],
        "solution of": [
            {"entity_id": "sol1", "value": "req1"},
        ],
        "todo": [
            {"entity_id": "todo_only", "value": "Something to follow up on later."},
        ],
    })


@pytest.mark.skip(
    reason=(
        "Documents a known gap (PR#96 review comment 3 / task #26), not yet fixed: "
        "the traceability audit doesn't have its own concept of 'unvalidated solution' "
        "-- it flags anything lacking both `requirement` and `solution of` as a generic "
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
