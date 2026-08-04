"""Tests for the audit.report dataflow (HTML audit report generation)."""

import json
import re

from iacs.dataflows.audit.report import (
    _json_safe,
    cost_impact_data,
    report_html,
    report_path,
)
from iacs.registrar import Registrar
from tests.conftest import make_registry


def _impact_cost_registry():
    return make_registry({
        "entity_id": [
            {"value": "e1", "entity_key": "high_impact_activity"},
            {"value": "e2", "entity_key": "high_cost_activity"},
        ],
        "resolved_impact_cost": [
            {"entity_id": "e1", "impact": 4.0, "cost": 1.0, "diff": 3.0, "ratio": 4.0},
            {"entity_id": "e2", "impact": 1.0, "cost": 5.0, "diff": -4.0, "ratio": 0.2},
        ],
    })


class TestCostImpactData:

    def test_resolves_labels_and_keeps_values(self):
        registry = _impact_cost_registry()
        rows = cost_impact_data(
            registry.get("resolved_impact_cost"), registry.get("entity_id")
        )
        by_label = {r["label"]: r for r in rows}
        assert set(by_label) == {"high_impact_activity", "high_cost_activity"}
        assert by_label["high_impact_activity"]["impact"] == 4.0
        assert by_label["high_impact_activity"]["diff"] == 3.0
        assert by_label["high_cost_activity"]["ratio"] == 0.2

    def test_empty_table_returns_empty_list(self):
        # No resolved_impact_cost table at all -> Registry's generic empty
        # entity_id/value fallback schema, which cost_impact_data must handle.
        registry = make_registry({
            "entity_id": [{"value": "e1", "entity_key": "e1"}],
        })
        rows = cost_impact_data(
            registry.get("resolved_impact_cost"), registry.get("entity_id")
        )
        assert rows == []


class TestJsonSafe:

    def test_replaces_non_finite_floats_with_none(self):
        data = [{"label": "a", "ratio": float("inf")}, {"label": "b", "ratio": float("nan")}]
        cleaned = _json_safe(data)
        assert cleaned[0]["ratio"] is None
        assert cleaned[1]["ratio"] is None
        # Must be directly JSON-serializable with no Infinity/NaN tokens.
        assert "Infinity" not in json.dumps(cleaned)
        assert "NaN" not in json.dumps(cleaned)

    def test_leaves_finite_values_untouched(self):
        data = [{"label": "a", "ratio": 1.5}]
        assert _json_safe(data) == data


class TestReportHtml:

    def test_embeds_cost_impact_and_tree_data(self):
        tree = {"name": "root_req", "priority": 1.0}
        rows = [{"label": "act", "impact": 1.0, "cost": 2.0, "diff": -1.0, "ratio": 0.5}]
        html = report_html(tree, rows)

        assert "<title>iacs Audit Report</title>" in html
        assert "root_req" in html
        assert "act" in html

        match = re.search(r"const costImpactData = (\[.*?\]);", html)
        assert match is not None
        assert json.loads(match.group(1)) == rows

        match = re.search(r"const requirementTreeData = (\{.*?\});", html)
        assert match is not None
        assert json.loads(match.group(1)) == tree

    def test_handles_empty_cost_impact_data(self):
        html = report_html({"name": "Requirements", "priority": None}, [])
        assert "No impact/cost data available." in html

    def test_escapes_script_breakout_in_labels(self):
        """A label containing '</script>' must not be able to close the embedding
        <script> tag early (classic JSON-in-HTML injection)."""
        rows = [{"label": "</script><script>bad</script>", "impact": 1.0, "cost": 1.0, "diff": 0.0, "ratio": 1.0}]
        html = report_html({"name": "Requirements", "priority": None}, rows)
        assert "</script><script>bad" not in html
        assert "\\u003c/script\\u003e" in html


class TestReportPath:

    def test_writes_file_and_returns_path(self, tmp_path):
        out = tmp_path / "nested" / "report.html"
        path = report_path("<html>hi</html>", str(out))
        assert path == str(out)
        assert out.read_text(encoding="utf-8") == "<html>hi</html>"


class TestGenerateReportEndToEnd:

    def test_generate_report_from_example_manifest(self, tmp_path):
        registrar = Registrar.from_manifest("examples/impact-cost_analysis")
        out = tmp_path / "report.html"
        path = registrar.generate_report(str(out))

        assert path == str(out)
        content = out.read_text(encoding="utf-8")
        assert "<title>iacs Audit Report</title>" in content
        assert "costImpactData" in content
        assert "requirementTreeData" in content
        # Real impact/cost data should have produced non-empty rows.
        match = re.search(r"const costImpactData = (\[.*?\]);", content)
        assert json.loads(match.group(1))
