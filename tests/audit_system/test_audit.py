import ibis
import pytest

from iacs.audit_system import AuditRunner
from iacs.registry import Registry
from iacs.transforms import audit_requirement_coverage, audit_traceability, audit_todo

from tests.conftest import make_registry


class TestAuditRunner:
    """Tests for AuditRunner."""

    def test_audit_runner_can_be_created_with_modules(self):
        """AuditRunner can be initialized with a list of modules."""
        runner = AuditRunner(audit_modules=[audit_todo])

        assert len(runner.audit_modules) == 1

    def test_audit_runner_run_returns_dict_of_ibis_tables(self):
        """AuditRunner.run returns a dict mapping audit names to ibis Tables."""
        runner = AuditRunner(audit_modules=[audit_todo])
        registry = Registry(ibis.duckdb.connect(), {})

        results = runner.run(registry)

        assert isinstance(results, dict)
        assert "todo" in results
        assert isinstance(results["todo"], ibis.expr.types.Table)

    def test_audit_runner_runs_all_modules(self):
        """AuditRunner runs all registered audit modules."""
        runner = AuditRunner(audit_modules=[audit_requirement_coverage, audit_todo])
        registry = Registry(ibis.duckdb.connect(), {})

        results = runner.run(registry)

        assert "requirement_coverage" in results
        assert "todo" in results

    def test_audit_runner_all_passed_property(self):
        """AuditRunner has all_passed property for quick check."""
        runner = AuditRunner(audit_modules=[audit_todo])
        registry = Registry(ibis.duckdb.connect(), {})

        runner.run(registry)

        assert hasattr(runner, "all_passed")
        assert runner.all_passed is True


class TestAuditRunnerWithRegistry:
    """Tests for AuditRunner with actual Registry data."""

    @pytest.fixture
    def sample_registry(self):
        """Create a registry with sample data."""
        return make_registry({
            "description": [
                {"entity_id": "my_task", "value": "A task to complete."},
                {"entity_id": "my_solution", "value": "Solution for the task."},
            ],
            "requirement": [
                {"entity_id": "my_task"},
            ],
            "solution of": [
                {"entity_id": "my_solution", "value": "my_task"},
            ],
        })

    def test_audit_runner_with_sample_data(self, sample_registry):
        """AuditRunner can process a registry with data."""
        runner = AuditRunner(audit_modules=[audit_todo])

        results = runner.run(sample_registry)

        assert results["todo"].count().execute() == 0
