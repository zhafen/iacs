"""Tests for iacs's own Registrar: the emc2p subclass wiring (extended
derive pipeline, dataflow package/builtins registration, generate_report).

Generic Registrar/Registry behavior (execute, outputs, save/load, manifest
loading, updates, ...) is covered by emc2p's own test suite -- this module
only covers what iacs adds on top.
"""

from pathlib import Path

import ibis

from tests.conftest import make_registry
from tests.test_dataflows.dags import dataflow
from iacs.registrar import Registrar


def _sample_registry():
    return make_registry(
        {
            "description": [
                {"entity_id": "e1", "value": "First entity"},
                {"entity_id": "e2", "value": "Second entity"},
            ]
        }
    )


class TestExecuteStillWorksOnSubclass:
    """Sanity check that emc2p's generic Registrar.execute machinery
    (Hamilton driver over arbitrary loaded dataflow modules) still works
    unmodified through iacs's subclass."""

    def test_execute_returns_expected_data(self):
        a = Registrar(_sample_registry())
        a._dataflows = [dataflow]
        result = a.execute(["entity_summary"])
        assert isinstance(result["entity_summary"], ibis.expr.types.Table)
        assert len(result["entity_summary"].execute()) == 2


class TestLoadDataflowResolvesIacsPackage:
    """iacs registers its own "iacs.dataflows" package with emc2p's
    resolve_dataflow (see iacs/__init__.py), so dotted names like
    "audit.requirement_coverage" resolve even though they don't live
    under emc2p.dataflows."""

    def test_load_iacs_subpackage_dataflow(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.requirement_coverage")
        assert any(
            m.__name__ == "iacs.dataflows.audit.requirement_coverage"
            for m in a._dataflows
        )

    def test_load_dataflow_adds_outputs(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.traceability")
        assert "traceability" in a.outputs

    def test_load_multiple_audit_dataflows(self):
        a = Registrar(_sample_registry())
        a.load_dataflow("audit.traceability")
        a.load_dataflow("audit.todo")
        assert "traceability" in a.outputs
        assert "todo" in a.outputs


class TestExtendedDerivePipeline:
    """update()/from_manifest() must run iacs's own base_etl (emc2p's
    generic derive pipeline + impact_cost), not emc2p's bare one -- this
    is the whole point of iacs.registrar.Registrar._base_etl_module."""

    def test_impact_cost_components_are_derived_automatically(self):
        a = Registrar()
        a.update(yaml_strings={
            "batch": (
                "req_a:\n"
                "    - description: Requirement A\n"
                "    - requirement_priority: 0.5\n"
            )
        })
        # resolved_impact_cost/priority_product only exist if impact_cost's
        # own dataflow ran as part of the default derive pipeline.
        assert "resolved_impact_cost" in a.registry.component_types
        assert "priority_product" in a.registry.component_types

    def test_iacs_builtins_component_types_are_known_without_manifest(self):
        """iacs's own builtins dir (requirement, task, audit.*, ...) is
        auto-included by emc2p's load_manifest the same way emc2p's own
        builtins/ is, via register_builtins_dir."""
        a = Registrar()
        a.update(yaml_strings={"empty": "placeholder:\n    - description: x\n"})
        assert "requirement" in a.registry.known_component_types
        assert "todo" in a.registry.known_component_types


class TestGenerateReport:
    def test_generate_report_writes_file(self, tmp_path):
        a = Registrar.from_manifest("examples/example")
        out = tmp_path / "report.html"
        path = a.generate_report(str(out))
        assert Path(path).exists()
