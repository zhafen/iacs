import ibis
import pandas as pd
import pytest

from iacs.audit_system import AuditResult, AuditRunner
from iacs.registry import Registry
from iacs.transforms import audit_requirement_coverage, audit_traceability, audit_todo

from tests.conftest import make_registry


class TestAuditResult:
    """Tests for AuditResult structure."""

    def test_audit_result_has_passed_attribute(self):
        """AuditResult has a passed boolean attribute."""
        result = AuditResult(passed=True)

        assert hasattr(result, "passed")
        assert result.passed is True

    def test_audit_result_has_messages_attribute(self):
        """AuditResult has a messages list attribute."""
        result = AuditResult(passed=True, messages=["All checks passed."])

        assert hasattr(result, "messages")
        assert result.messages == ["All checks passed."]

    def test_audit_result_messages_default_to_empty_list(self):
        """AuditResult messages default to empty list."""
        result = AuditResult(passed=True)

        assert result.messages == []

    def test_audit_result_has_results_attribute(self):
        """AuditResult has a results DataFrame for flagged records."""
        results_df = pd.DataFrame({"entity_id": ["entity_a", "entity_b"]})
        result = AuditResult(passed=False, results=results_df)

        assert hasattr(result, "results")
        assert isinstance(result.results, pd.DataFrame)
        assert len(result.results) == 2

    def test_audit_result_results_default_to_empty_dataframe(self):
        """AuditResult results default to empty DataFrame."""
        result = AuditResult(passed=True)

        assert isinstance(result.results, pd.DataFrame)
        assert result.results.empty

    def test_audit_result_view_returns_ibis_table(self):
        """AuditResult.view() returns an Ibis table from results."""
        results_df = pd.DataFrame({"entity_id": ["entity_a", "entity_b"]})
        result = AuditResult(passed=False, results=results_df)

        table = result.view()

        assert isinstance(table, ibis.expr.types.Table)
        assert table.count().execute() == 2
        assert "entity_id" in table.columns

    def test_audit_result_view_empty_results(self):
        """AuditResult.view() returns an empty Ibis table when results are empty."""
        result = AuditResult(passed=True)

        table = result.view()

        assert isinstance(table, ibis.expr.types.Table)
        assert table.count().execute() == 0

    def test_audit_result_view_preserves_columns(self):
        """AuditResult.view() preserves all columns from results."""
        results_df = pd.DataFrame({
            "entity_id": ["entity_a"],
            "extra_info": ["some detail"],
        })
        result = AuditResult(passed=False, results=results_df)

        table = result.view()

        assert "entity_id" in table.columns
        assert "extra_info" in table.columns


class TestAuditRunner:
    """Tests for AuditRunner."""

    def test_audit_runner_can_be_created_with_modules(self):
        """AuditRunner can be initialized with a list of modules."""
        runner = AuditRunner(audit_modules=[audit_todo])

        assert len(runner.audit_modules) == 1

    def test_audit_runner_run_returns_dict_of_results(self):
        """AuditRunner.run returns a dict mapping audit names to results."""
        runner = AuditRunner(audit_modules=[audit_todo])
        registry = Registry(ibis.duckdb.connect(), {})

        results = runner.run(registry)

        assert isinstance(results, dict)
        assert "todo" in results
        assert isinstance(results["todo"], AuditResult)

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

        assert results["todo"].passed is True
