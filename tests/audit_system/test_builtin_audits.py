import hashlib

from iacs.audit_system import (
    RequirementCoverageAudit,
    TraceabilityAudit,
    TodoAudit,
)
from iacs.io_system import IOSystem
from iacs.registry import Registry


def eid(path: str) -> str:
    """Compute the expected entity_id for a given path (no alias)."""
    return hashlib.md5(path.encode()).hexdigest()[:12]


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

    def test_passes_when_requirement_has_solution(self):
        """Passes when requirement has a solution."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_task": [
                {"description": "A requirement."},
                "requirement",
            ],
            "my_solution": [
                {"description": "Solves the requirement."},
                {"solution of": "my_task"},
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True

    def test_fails_when_requirement_missing_solution(self):
        """Fails when a requirement has no solution."""
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
        """Flags the entity ID of uncovered requirements in results."""
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

        assert eid("uncovered_req") in result.results["entity_id"].values

    def test_multiple_requirements_all_covered(self):
        """Passes when all requirements have solutions."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "req_a": [{"description": "Requirement A."}, "requirement"],
            "req_b": [{"description": "Requirement B."}, "requirement"],
            "solution_a": [{"solution of": "req_a"}],
            "solution_b": [{"solution of": "req_b"}],
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
            "solution_a": [{"solution of": "req_a"}],
            # req_b has no solution
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is False
        assert eid("req_b") in result.results["entity_id"].values
        assert eid("req_a") not in result.results["entity_id"].values

    def test_passes_when_parent_requirement_has_child_requirements(self):
        """Parent requirement is covered if it has child requirements."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "parent_req": {
                "data": [
                    {"description": "A parent requirement."},
                    "requirement",
                ],
                "child_req": [
                    {"description": "A child requirement."},
                    "requirement",
                ],
            },
            "solution": [{"solution of": "parent_req.child_req"}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True
        assert result.results.empty or eid("parent_req") not in result.results["entity_id"].values

    def test_fails_when_leaf_requirement_has_no_solution(self):
        """Leaf requirement (no children) without solution fails."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "parent_req": {
                "data": [
                    {"description": "A parent requirement."},
                    "requirement",
                ],
                "child_req": [
                    {"description": "A child requirement with no solution."},
                    "requirement",
                ],
            },
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is False
        assert eid("parent_req.child_req") in result.results["entity_id"].values
        assert eid("parent_req") not in result.results["entity_id"].values

    def test_deeply_nested_requirements_covered_by_hierarchy(self):
        """Deeply nested requirements are covered by having children."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "level1": {
                "data": [{"description": "Level 1."}, "requirement"],
                "level2": {
                    "data": [{"description": "Level 2."}, "requirement"],
                    "level3": [
                        {"description": "Level 3 leaf."},
                        "requirement",
                    ],
                },
            },
            "solution": [{"solution of": "level1.level2.level3"}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = RequirementCoverageAudit()

        result = audit.run(registry)

        assert result.passed is True


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

    def test_passes_when_entity_has_solution(self):
        """Passes when non-requirement entity has a solution of component."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_req": [{"description": "A requirement."}, "requirement"],
            "my_solution": [
                {"description": "Solves the requirement."},
                {"solution of": "my_req"},
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
                {"description": "No requirement or solution."},
            ],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert result.passed is False

    def test_flags_orphan_entity(self):
        """Flags entity IDs that don't trace to requirements in results."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "orphan_entity": [{"description": "No trace."}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TraceabilityAudit()

        result = audit.run(registry)

        assert eid("orphan_entity") in result.results["entity_id"].values


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
        """Flags entity IDs that have todo components in results."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "entity_with_todo": [{"todo": "Do something."}],
            "entity_without_todo": [{"description": "Clean."}],
        })
        registry = Registry.from_entity_centered(entity_centered)
        audit = TodoAudit()

        result = audit.run(registry)

        assert eid("entity_with_todo") in result.results["entity_id"].values
        assert eid("entity_without_todo") not in result.results["entity_id"].values

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
