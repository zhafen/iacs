"""Tests for iacs.views.architecture_graph."""

from tests.conftest import make_registry
from iacs.views.architecture_graph import build_architecture_graph, render_mermaid


def _registry(entity_id_rows, calls_rows=None, imports_rows=None):
    components = {"entity_id": entity_id_rows}
    if calls_rows:
        components["calls"] = calls_rows
    if imports_rows:
        components["imports"] = imports_rows
    return make_registry(components)


# ---------------------------------------------------------------------------
# build_architecture_graph
# ---------------------------------------------------------------------------

class TestBuildArchitectureGraph:

    def test_entities_without_filepath_info_return_empty_graph(self):
        # An empty entity_id_rows list can't even build a DuckDB table (no
        # columns to infer), so this uses a row that simply lacks the
        # `filepath` key -- the resulting table has no `filepath` column at
        # all, the same "nothing to group by" case in practice.
        registry = _registry(entity_id_rows=[{"value": "e1", "entity_key": "e1"}])
        graph = build_architecture_graph(registry)
        assert graph == {"nodes": [], "edges": []}

    def test_entities_with_no_calls_or_imports_produce_nodes_but_no_edges(self):
        registry = _registry(entity_id_rows=[
            {"value": "e1", "entity_key": "foo", "filepath": "pkg/mod.py"},
        ])
        graph = build_architecture_graph(registry)
        assert graph["nodes"] == [{"id": "pkg/mod.py", "label": "mod"}]
        assert graph["edges"] == []

    def test_resolved_call_across_files_becomes_an_edge(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "caller_e", "entity_key": "main", "filepath": "pkg/a.py"},
                {"value": "callee_e", "entity_key": "helper", "filepath": "pkg/b.py"},
            ],
            calls_rows=[
                {"entity_id": "caller_e", "value": "helper", "value_eid": "callee_e"},
            ],
        )
        graph = build_architecture_graph(registry)
        assert {"id": "pkg/a.py", "label": "a"} in graph["nodes"]
        assert {"id": "pkg/b.py", "label": "b"} in graph["nodes"]
        assert graph["edges"] == [
            {"source": "pkg/a.py", "target": "pkg/b.py", "kind": "calls"},
        ]

    def test_unresolved_call_produces_no_edge(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "caller_e", "entity_key": "main", "filepath": "pkg/a.py"},
            ],
            calls_rows=[
                # A None value_eid (no unique entity_ref match) and a
                # value_eid pointing at an entity outside this registry
                # entirely both fail to resolve to a known filepath.
                {"entity_id": "caller_e", "value": "os.getcwd", "value_eid": None},
                {"entity_id": "caller_e", "value": "other", "value_eid": "unknown_id"},
            ],
        )
        graph = build_architecture_graph(registry)
        assert graph["edges"] == []

    def test_call_within_same_file_is_dropped_as_a_self_edge(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "caller_e", "entity_key": "main", "filepath": "pkg/a.py"},
                {"value": "callee_e", "entity_key": "helper", "filepath": "pkg/a.py"},
            ],
            calls_rows=[
                {"entity_id": "caller_e", "value": "helper", "value_eid": "callee_e"},
            ],
        )
        graph = build_architecture_graph(registry)
        assert graph["edges"] == []

    def test_duplicate_calls_between_same_files_collapse_to_one_edge(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "caller1", "entity_key": "main", "filepath": "pkg/a.py"},
                {"value": "caller2", "entity_key": "other", "filepath": "pkg/a.py"},
                {"value": "callee_e", "entity_key": "helper", "filepath": "pkg/b.py"},
            ],
            calls_rows=[
                {"entity_id": "caller1", "value": "helper", "value_eid": "callee_e"},
                {"entity_id": "caller2", "value": "helper", "value_eid": "callee_e"},
            ],
        )
        graph = build_architecture_graph(registry)
        assert graph["edges"] == [
            {"source": "pkg/a.py", "target": "pkg/b.py", "kind": "calls"},
        ]

    def test_resolved_import_becomes_an_imports_edge(self):
        registry = _registry(
            entity_id_rows=[
                {"value": "mod_e", "entity_key": "a", "filepath": "pkg/a.py"},
                {"value": "dep_e", "entity_key": "b", "filepath": "pkg/b.py"},
            ],
            imports_rows=[
                {"entity_id": "mod_e", "value": "pkg.b", "value_eid": "dep_e"},
            ],
        )
        graph = build_architecture_graph(registry)
        assert graph["edges"] == [
            {"source": "pkg/a.py", "target": "pkg/b.py", "kind": "imports"},
        ]

    def test_non_python_filepaths_are_excluded(self):
        """calls/imports only ever come from parsed .py files -- a YAML-sourced
        entity (e.g. a requirement or component-type definition) has no place
        in a call/import graph and would only ever show up as edgeless
        clutter, so it's filtered out rather than surfaced as a node."""
        registry = _registry(entity_id_rows=[
            {"value": "e1", "entity_key": "foo", "filepath": "pkg/mod.py"},
            {"value": "e2", "entity_key": "bar", "filepath": "manifest/builtins.yaml"},
        ])
        graph = build_architecture_graph(registry)
        assert graph["nodes"] == [{"id": "pkg/mod.py", "label": "mod"}]

    def test_nodes_are_sorted_by_filepath(self):
        registry = _registry(entity_id_rows=[
            {"value": "e1", "entity_key": "z", "filepath": "pkg/z.py"},
            {"value": "e2", "entity_key": "a", "filepath": "pkg/a.py"},
        ])
        graph = build_architecture_graph(registry)
        assert [n["id"] for n in graph["nodes"]] == ["pkg/a.py", "pkg/z.py"]


# ---------------------------------------------------------------------------
# render_mermaid
# ---------------------------------------------------------------------------

class TestRenderMermaid:

    def test_empty_graph_renders_placeholder(self):
        out = render_mermaid({"nodes": [], "edges": []})
        assert out.startswith("flowchart LR")
        assert "no entities" in out

    def test_renders_a_node_per_entry(self):
        graph = {"nodes": [{"id": "pkg/a.py", "label": "a"}], "edges": []}
        out = render_mermaid(graph)
        assert '["a"]' in out

    def test_calls_edge_uses_solid_arrow(self):
        graph = {
            "nodes": [{"id": "pkg/a.py", "label": "a"}, {"id": "pkg/b.py", "label": "b"}],
            "edges": [{"source": "pkg/a.py", "target": "pkg/b.py", "kind": "calls"}],
        }
        out = render_mermaid(graph)
        assert "-->" in out
        assert "-.->" not in out

    def test_imports_edge_uses_dashed_arrow(self):
        graph = {
            "nodes": [{"id": "pkg/a.py", "label": "a"}, {"id": "pkg/b.py", "label": "b"}],
            "edges": [{"source": "pkg/a.py", "target": "pkg/b.py", "kind": "imports"}],
        }
        out = render_mermaid(graph)
        assert "-.->" in out

    def test_filepath_ids_are_remapped_to_safe_mermaid_identifiers(self):
        """Mermaid node IDs can't contain slashes/dots -- raw filepaths must not appear as IDs."""
        graph = {
            "nodes": [{"id": "pkg/sub.mod.py", "label": "sub.mod"}],
            "edges": [],
        }
        out = render_mermaid(graph)
        assert "pkg/sub.mod.py" not in out
