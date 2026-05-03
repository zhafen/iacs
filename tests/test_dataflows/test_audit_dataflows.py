"""Tests for the audit dataflows (todo, traceability, requirement_coverage)."""

import ibis
import pytest

from iacs.architect import Architect
from tests.conftest import make_registry


EXAMPLE_MANIFEST = "examples/example"


def _architect_with_audits(*dataflow_names):
    a = Architect.from_manifest(EXAMPLE_MANIFEST)
    for name in dataflow_names:
        a.load_dataflow(name)
    return a


class TestTodoAudit:
    def test_todo_returns_table(self):
        a = _architect_with_audits("audit.todo")
        result = a.execute(["todo"])
        assert isinstance(result["todo"], ibis.expr.types.Table)

    def test_todo_has_expected_columns(self):
        a = _architect_with_audits("audit.todo")
        result = a.execute(["todo"])
        cols = result["todo"].columns
        assert "entity_id" in cols
        assert "value" in cols

    def test_todo_empty_registry_returns_empty_table(self):
        a = Architect(make_registry({"description": [{"entity_id": "e1", "value": "x"}]}))
        a.load_dataflow("audit.todo")
        result = a.execute(["todo"])
        df = result["todo"].execute()
        assert len(df) == 0


class TestTraceabilityAudit:
    def test_traceability_returns_table(self):
        a = _architect_with_audits("audit.traceability")
        result = a.execute(["traceability"])
        assert isinstance(result["traceability"], ibis.expr.types.Table)

    def test_traceability_has_expected_columns(self):
        a = _architect_with_audits("audit.traceability")
        result = a.execute(["traceability"])
        cols = result["traceability"].columns
        assert "entity_id" in cols
        assert "message" in cols

    def test_traceability_empty_registry_returns_empty_table(self):
        a = Architect(make_registry({}))
        a.load_dataflow("audit.traceability")
        result = a.execute(["traceability"])
        df = result["traceability"].execute()
        assert len(df) == 0


class TestRequirementCoverageAudit:
    def test_requirement_coverage_runs_on_example_manifest(self):
        a = _architect_with_audits("audit.requirement_coverage")
        # This exercises load + execute without error; catches missing component types.
        result = a.execute(["requirement_coverage"])
        assert "requirement_coverage" in result

    def test_requirement_coverage_returns_table(self):
        a = _architect_with_audits("audit.requirement_coverage")
        result = a.execute(["requirement_coverage"])
        assert isinstance(result["requirement_coverage"], ibis.expr.types.Table)

    def test_requirement_coverage_has_expected_columns(self):
        a = _architect_with_audits("audit.requirement_coverage")
        result = a.execute(["requirement_coverage"])
        cols = result["requirement_coverage"].columns
        assert "entity_id" in cols

    def test_solution_with_state_returns_table(self):
        from iacs.dataflows.audit import requirement_coverage as rc
        import importlib
        from hamilton import driver, base

        a = Architect.from_manifest(EXAMPLE_MANIFEST)
        inputs = {"registry": a.registry}
        dr = driver.Driver(inputs, rc, adapter=base.DictResult())
        result = dr.execute(["solution_with_state"])
        assert isinstance(result["solution_with_state"], ibis.expr.types.Table)
