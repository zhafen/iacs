import ibis

from iacs.transforms.audit_requirement_coverage import (
    requirement_entities,
    parents_with_req_children,
    solved_requirements,
    uncovered_requirements,
    requirement_coverage,
)
from iacs.transforms.audit_traceability import (
    all_entities,
    req_entities,
    solution_entities,
    orphan_entities,
    traceability,
)
from iacs.transforms.audit_todo import (
    todo_table,
    todo,
)
from iacs.registry import Registry

from tests.conftest import make_registry


class TestRequirementCoverageAudit:
    """Tests for requirement coverage audit DAG."""

    def _run(self, registry):
        """Run the full requirement coverage DAG."""
        re = requirement_entities(registry)
        pwrc = parents_with_req_children(registry, re)
        sr = solved_requirements(registry)
        ur = uncovered_requirements(re, pwrc, sr)
        return requirement_coverage(ur)

    def test_passes_when_no_requirements(self):
        """Passes when there are no requirements to cover."""
        registry = make_registry({
            "description": [{"entity_id": "my_entity", "value": "Just a description."}],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_passes_when_requirement_has_solution(self):
        """Passes when requirement has a solution."""
        registry = make_registry({
            "description": [
                {"entity_id": "my_task", "value": "A requirement."},
                {"entity_id": "my_solution", "value": "Solves the requirement."},
            ],
            "requirement": [{"entity_id": "my_task"}],
            "solution of": [{"entity_id": "my_solution", "value": "my_task"}],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_fails_when_requirement_missing_solution(self):
        """Fails when a requirement has no solution."""
        registry = make_registry({
            "description": [{"entity_id": "my_task", "value": "A requirement with no solution."}],
            "requirement": [{"entity_id": "my_task"}],
        })

        result = self._run(registry)

        assert result.passed is False

    def test_flags_uncovered_requirement_entity(self):
        """Flags the entity ID of uncovered requirements in results."""
        registry = make_registry({
            "description": [{"entity_id": "uncovered_req", "value": "No solution for this."}],
            "requirement": [{"entity_id": "uncovered_req"}],
        })

        result = self._run(registry)

        assert "uncovered_req" in result.results["entity_id"].values

    def test_multiple_requirements_all_covered(self):
        """Passes when all requirements have solutions."""
        registry = make_registry({
            "requirement": [
                {"entity_id": "req_a"},
                {"entity_id": "req_b"},
            ],
            "solution of": [
                {"entity_id": "solution_a", "value": "req_a"},
                {"entity_id": "solution_b", "value": "req_b"},
            ],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_multiple_requirements_some_uncovered(self):
        """Fails and flags only uncovered requirements."""
        registry = make_registry({
            "requirement": [
                {"entity_id": "req_a"},
                {"entity_id": "req_b"},
            ],
            "solution of": [
                {"entity_id": "solution_a", "value": "req_a"},
            ],
        })

        result = self._run(registry)

        assert result.passed is False
        assert "req_b" in result.results["entity_id"].values
        assert "req_a" not in result.results["entity_id"].values

    def test_passes_when_parent_requirement_has_child_requirements(self):
        """Parent requirement is covered if it has child requirements."""
        registry = make_registry({
            "description": [
                {"entity_id": "parent_req", "value": "A parent requirement."},
                {"entity_id": "child_req", "value": "A child requirement."},
            ],
            "requirement": [
                {"entity_id": "parent_req"},
                {"entity_id": "child_req"},
            ],
            "parent": [
                {"entity_id": "child_req", "source": "child_req", "target": "parent_req"},
            ],
            "solution of": [
                {"entity_id": "solution", "value": "child_req"},
            ],
        })

        result = self._run(registry)

        assert result.passed is True
        assert result.results.empty or "parent_req" not in result.results["entity_id"].values

    def test_fails_when_leaf_requirement_has_no_solution(self):
        """Leaf requirement (no children) without solution fails."""
        registry = make_registry({
            "description": [
                {"entity_id": "parent_req", "value": "A parent requirement."},
                {"entity_id": "child_req", "value": "A child requirement with no solution."},
            ],
            "requirement": [
                {"entity_id": "parent_req"},
                {"entity_id": "child_req"},
            ],
            "parent": [
                {"entity_id": "child_req", "source": "child_req", "target": "parent_req"},
            ],
        })

        result = self._run(registry)

        assert result.passed is False
        assert "child_req" in result.results["entity_id"].values
        assert "parent_req" not in result.results["entity_id"].values

    def test_deeply_nested_requirements_covered_by_hierarchy(self):
        """Deeply nested requirements are covered by having children."""
        registry = make_registry({
            "requirement": [
                {"entity_id": "level1"},
                {"entity_id": "level2"},
                {"entity_id": "level3"},
            ],
            "parent": [
                {"entity_id": "level2", "source": "level2", "target": "level1"},
                {"entity_id": "level3", "source": "level3", "target": "level2"},
            ],
            "solution of": [
                {"entity_id": "solution", "value": "level3"},
            ],
        })

        result = self._run(registry)

        assert result.passed is True


class TestTraceabilityAudit:
    """Tests for traceability audit DAG."""

    def _run(self, registry):
        """Run the full traceability DAG."""
        ae = all_entities(registry)
        re = req_entities(registry)
        se = solution_entities(registry)
        oe = orphan_entities(ae, re, se)
        return traceability(oe)

    def test_passes_when_empty_registry(self):
        """Passes when registry is empty."""
        registry = Registry(ibis.duckdb.connect(), {})

        result = self._run(registry)

        assert result.passed is True

    def test_passes_when_all_entities_are_requirements(self):
        """Passes when all entities are requirements (no orphans)."""
        registry = make_registry({
            "requirement": [{"entity_id": "req_a"}],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_passes_when_entity_has_solution(self):
        """Passes when non-requirement entity has a solution of component."""
        registry = make_registry({
            "requirement": [{"entity_id": "my_req"}],
            "solution of": [{"entity_id": "my_solution", "value": "my_req"}],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_fails_when_entity_has_no_requirement_trace(self):
        """Fails when an entity doesn't trace to any requirement."""
        registry = make_registry({
            "description": [{"entity_id": "orphan_entity", "value": "No requirement or solution."}],
        })

        result = self._run(registry)

        assert result.passed is False

    def test_flags_orphan_entity(self):
        """Flags entity IDs that don't trace to requirements in results."""
        registry = make_registry({
            "description": [{"entity_id": "orphan_entity", "value": "No trace."}],
        })

        result = self._run(registry)

        assert "orphan_entity" in result.results["entity_id"].values


class TestTodoAudit:
    """Tests for todo audit DAG."""

    def _run(self, registry):
        """Run the full todo DAG."""
        tt = todo_table(registry)
        return todo(tt)

    def test_passes_when_no_todos(self):
        """Passes when there are no todo components."""
        registry = make_registry({
            "description": [{"entity_id": "my_entity", "value": "No todos here."}],
        })

        result = self._run(registry)

        assert result.passed is True

    def test_fails_when_todos_exist(self):
        """Fails when there are outstanding todos."""
        registry = make_registry({
            "description": [{"entity_id": "my_entity", "value": "Has a todo."}],
            "todo": [{"entity_id": "my_entity", "value": "Fix this thing."}],
        })

        result = self._run(registry)

        assert result.passed is False

    def test_flags_entities_with_todos(self):
        """Flags entity IDs that have todo components in results."""
        registry = make_registry({
            "todo": [{"entity_id": "entity_with_todo", "value": "Do something."}],
            "description": [{"entity_id": "entity_without_todo", "value": "Clean."}],
        })

        result = self._run(registry)

        assert "entity_with_todo" in result.results["entity_id"].values
        assert "entity_without_todo" not in result.results["entity_id"].values

    def test_reports_todo_content_in_messages(self):
        """Reports todo content in messages."""
        registry = make_registry({
            "todo": [{"entity_id": "my_entity", "value": "Remember to refactor."}],
        })

        result = self._run(registry)

        assert any("Remember to refactor" in msg for msg in result.messages)
