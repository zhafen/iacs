import ibis
import pandas as pd
import pytest

from iacs.audit_system import Audit, AuditResult, AuditRunner
from iacs.registry import Registry

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


class TestAuditInterface:
    """Tests for the Audit base class interface."""

    def test_audit_has_name_attribute(self):
        """Audit has a name attribute."""
        audit = Audit(name="test_audit")

        assert audit.name == "test_audit"

    def test_audit_has_run_method(self):
        """Audit has a run method that takes a Registry."""
        audit = Audit(name="test_audit")

        assert hasattr(audit, "run")
        assert callable(audit.run)

    def test_audit_run_returns_audit_result(self):
        """Audit.run returns an AuditResult."""
        audit = Audit(name="test_audit")
        registry = Registry(ibis.duckdb.connect(), {})

        result = audit.run(registry)

        assert isinstance(result, AuditResult)

    def test_base_audit_passes_by_default(self):
        """Base Audit passes by default (no checks)."""
        audit = Audit(name="test_audit")
        registry = Registry(ibis.duckdb.connect(), {})

        result = audit.run(registry)

        assert result.passed is True


class TestAuditRunner:
    """Tests for AuditRunner."""

    def test_audit_runner_can_be_created_with_audits(self):
        """AuditRunner can be initialized with a list of audits."""
        audit1 = Audit(name="audit_1")
        audit2 = Audit(name="audit_2")

        runner = AuditRunner(audits=[audit1, audit2])

        assert len(runner.audits) == 2

    def test_audit_runner_run_returns_dict_of_results(self):
        """AuditRunner.run returns a dict mapping audit names to results."""
        audit = Audit(name="test_audit")
        runner = AuditRunner(audits=[audit])
        registry = Registry(ibis.duckdb.connect(), {})

        results = runner.run(registry)

        assert isinstance(results, dict)
        assert "test_audit" in results
        assert isinstance(results["test_audit"], AuditResult)

    def test_audit_runner_runs_all_audits(self):
        """AuditRunner runs all registered audits."""
        audit1 = Audit(name="audit_1")
        audit2 = Audit(name="audit_2")
        runner = AuditRunner(audits=[audit1, audit2])
        registry = Registry(ibis.duckdb.connect(), {})

        results = runner.run(registry)

        assert "audit_1" in results
        assert "audit_2" in results

    def test_audit_runner_all_passed_property(self):
        """AuditRunner has all_passed property for quick check."""
        audit = Audit(name="test_audit")
        runner = AuditRunner(audits=[audit])
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
        audit = Audit(name="test_audit")
        runner = AuditRunner(audits=[audit])

        results = runner.run(sample_registry)

        assert results["test_audit"].passed is True
