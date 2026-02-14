import pytest

from iacs.audit_system import Audit, AuditResult, AuditRunner
from iacs.io_system import IOSystem
from iacs.registry import Registry


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

    def test_audit_result_has_entities_attribute(self):
        """AuditResult has an entities list for flagged entity IDs."""
        result = AuditResult(passed=False, entities=["entity_a", "entity_b"])

        assert hasattr(result, "entities")
        assert result.entities == ["entity_a", "entity_b"]

    def test_audit_result_entities_default_to_empty_list(self):
        """AuditResult entities default to empty list."""
        result = AuditResult(passed=True)

        assert result.entities == []


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
        registry = Registry({})

        result = audit.run(registry)

        assert isinstance(result, AuditResult)

    def test_base_audit_passes_by_default(self):
        """Base Audit passes by default (no checks)."""
        audit = Audit(name="test_audit")
        registry = Registry({})

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
        registry = Registry({})

        results = runner.run(registry)

        assert isinstance(results, dict)
        assert "test_audit" in results
        assert isinstance(results["test_audit"], AuditResult)

    def test_audit_runner_runs_all_audits(self):
        """AuditRunner runs all registered audits."""
        audit1 = Audit(name="audit_1")
        audit2 = Audit(name="audit_2")
        runner = AuditRunner(audits=[audit1, audit2])
        registry = Registry({})

        results = runner.run(registry)

        assert "audit_1" in results
        assert "audit_2" in results

    def test_audit_runner_all_passed_property(self):
        """AuditRunner has all_passed property for quick check."""
        audit = Audit(name="test_audit")
        runner = AuditRunner(audits=[audit])
        registry = Registry({})

        runner.run(registry)

        assert hasattr(runner, "all_passed")
        assert runner.all_passed is True


class TestAuditRunnerWithRegistry:
    """Tests for AuditRunner with actual Registry data."""

    @pytest.fixture
    def sample_registry(self):
        """Create a registry with sample data."""
        io = IOSystem()
        entity_centered = io.read_entity_centered({
            "my_task": [
                {"description": "A task to complete."},
                "requirement",
            ],
            "my_solution": [
                {"description": "Solution for the task."},
                {"implements": "my_task"},
            ],
        })
        return Registry.from_entity_centered(entity_centered)

    def test_audit_runner_with_sample_data(self, sample_registry):
        """AuditRunner can process a registry with data."""
        audit = Audit(name="test_audit")
        runner = AuditRunner(audits=[audit])

        results = runner.run(sample_registry)

        assert results["test_audit"].passed is True
