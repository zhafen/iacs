import pytest

from iacs.audit_system import (
    AuditResult,
    RequirementCoverageAudit,
    TraceabilityAudit,
    TodoAudit,
)
from iacs.io_system import IOSystem
from iacs.registry import Registry


class TestRequirementCoverageAudit:
    """Tests for RequirementCoverageAudit."""

    def test_requirement_coverage_audit_has_correct_name(self):
        """RequirementCoverageAudit has the expected name."""
        audit = RequirementCoverageAudit()

        assert audit.name == "requirement_coverage"

    def test_passes_when_no_requirements(self):
        """Passes when there are no requirements to cover."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_entity": [{"description": "Just a description."}]
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_passes_when_requirement_has_implements(self):
        """Passes when requirement has an implementing solution."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_task": [
                {"description": "A requirement."},
                "requirement",
            ],
            "my_solution": [
                {"description": "Implements the requirement."},
                {"implements": "my_task"},
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_fails_when_requirement_missing_implements(self):
        """Fails when a requirement has no implementing solution."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_task": [
                {"description": "A requirement with no solution."},
                "requirement",
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is False

    def test_flags_uncovered_requirement_entity(self):
        """Flags the entity ID of uncovered requirements."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "uncovered_req": [
                {"description": "No solution for this."},
                "requirement",
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert "uncovered_req" in result.entities

    def test_multiple_requirements_all_covered(self):
        """Passes when all requirements have implementations."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "req_a": [{"description": "Requirement A."}, "requirement"],
            "req_b": [{"description": "Requirement B."}, "requirement"],
            "solution_a": [{"implements": "req_a"}],
            "solution_b": [{"implements": "req_b"}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_multiple_requirements_some_uncovered(self):
        """Fails and flags only uncovered requirements."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "req_a": [{"description": "Requirement A."}, "requirement"],
            "req_b": [{"description": "Requirement B."}, "requirement"],
            "solution_a": [{"implements": "req_a"}],
            # req_b has no solution
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is False
        assert "req_b" in result.entities
        assert "req_a" not in result.entities


class TestTraceabilityAudit:
    """Tests for TraceabilityAudit."""

    def test_traceability_audit_has_correct_name(self):
        """TraceabilityAudit has the expected name."""
        audit = TraceabilityAudit()

        assert audit.name == "traceability"

    def test_passes_when_empty_registry(self):
        """Passes when registry is empty."""
        registry = Registry({})
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_passes_when_all_entities_are_requirements(self):
        """Passes when all entities are requirements (no orphans)."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "req_a": [{"description": "A requirement."}, "requirement"],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_passes_when_entity_implements_requirement(self):
        """Passes when non-requirement entity implements a requirement."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_req": [{"description": "A requirement."}, "requirement"],
            "my_solution": [
                {"description": "Implements the requirement."},
                {"implements": "my_req"},
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_fails_when_entity_has_no_requirement_trace(self):
        """Fails when an entity doesn't trace to any requirement."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "orphan_entity": [
                {"description": "No requirement or implements."},
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert result.passed is False

    def test_flags_orphan_entity(self):
        """Flags entity IDs that don't trace to requirements."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "orphan_entity": [{"description": "No trace."}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert "orphan_entity" in result.entities


class TestTodoAudit:
    """Tests for TodoAudit."""

    def test_todo_audit_has_correct_name(self):
        """TodoAudit has the expected name."""
        audit = TodoAudit()

        assert audit.name == "todo"

    def test_passes_when_no_todos(self):
        """Passes when there are no todo components."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_entity": [{"description": "No todos here."}]
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TodoAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_fails_when_todos_exist(self):
        """Fails when there are outstanding todos."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_entity": [
                {"description": "Has a todo."},
                {"todo": "Fix this thing."},
            ]
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TodoAudit()

        result = audit.run(registry)

        assert result.passed is False

    def test_flags_entities_with_todos(self):
        """Flags entity IDs that have todo components."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "entity_with_todo": [{"todo": "Do something."}],
            "entity_without_todo": [{"description": "Clean."}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TodoAudit()

        result = audit.run(registry)

        assert "entity_with_todo" in result.entities
        assert "entity_without_todo" not in result.entities

    def test_reports_todo_content_in_messages(self):
        """Reports todo content in messages."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_entity": [{"todo": "Remember to refactor."}]
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TodoAudit()

        result = audit.run(registry)

        assert any("Remember to refactor" in msg for msg in result.messages)
