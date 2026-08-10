"""Tests for iacs.views.architecture_graph."""

import pytest

from tests.conftest import make_registry
from iacs.views.architecture_graph import (
    build_architecture_graph,
    build_call_reachability,
    render_mermaid,
    render_reachability_mermaid,
)


def _registry(entity_id_rows, calls_rows=None, imports_rows=None):
    components = {"entity_id": entity_id_rows}
    if calls_rows:
        components["calls"] = calls_rows
    if imports_rows:
        components["imports"] = imports_rows
    return make_registry(components)


def _reachability_registry(entity_id_rows, calls_rows=None):
    components = {"entity_id": entity_id_rows}
    if calls_rows:
        components["calls"] = calls_rows
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


# ---------------------------------------------------------------------------
# build_call_reachability
# ---------------------------------------------------------------------------

class TestBuildCallReachability:

    def test_root_alone_when_no_calls(self):
        registry = _reachability_registry(entity_id_rows=[
            {"value": "root_e", "entity_key": "main", "alias": "main",
             "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
        ])
        graph = build_call_reachability(registry, "main")
        assert graph["root"] == "root_e"
        assert graph["nodes"] == [
            {"id": "root_e", "label": "main", "filepath": "mod_a.py"},
        ]
        assert graph["edges"] == []

    def test_direct_call_is_included(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "helper_e", "entity_key": "helper", "alias": "helper",
                 "path": "mod_a.py:mod_a.helper", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "helper", "value_eid": "helper_e"},
            ],
        )
        graph = build_call_reachability(registry, "main")
        ids = {n["id"] for n in graph["nodes"]}
        assert ids == {"root_e", "helper_e"}
        assert graph["edges"] == [{"source": "root_e", "target": "helper_e"}]

    def test_transitive_call_two_hops_is_included(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "mid_e", "entity_key": "helper", "alias": "helper",
                 "path": "mod_a.py:mod_a.helper", "filepath": "mod_a.py"},
                {"value": "leaf_e", "entity_key": "util", "alias": "util",
                 "path": "mod_b.py:mod_b.util", "filepath": "mod_b.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "helper", "value_eid": "mid_e"},
                {"entity_id": "mid_e", "value": "util", "value_eid": "leaf_e"},
            ],
        )
        graph = build_call_reachability(registry, "main")
        ids = {n["id"] for n in graph["nodes"]}
        assert ids == {"root_e", "mid_e", "leaf_e"}
        assert {"source": "mid_e", "target": "leaf_e"} in graph["edges"]

    def test_max_depth_limits_traversal(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "mid_e", "entity_key": "helper", "alias": "helper",
                 "path": "mod_a.py:mod_a.helper", "filepath": "mod_a.py"},
                {"value": "leaf_e", "entity_key": "util", "alias": "util",
                 "path": "mod_b.py:mod_b.util", "filepath": "mod_b.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "helper", "value_eid": "mid_e"},
                {"entity_id": "mid_e", "value": "util", "value_eid": "leaf_e"},
            ],
        )
        graph = build_call_reachability(registry, "main", max_depth=1)
        ids = {n["id"] for n in graph["nodes"]}
        assert ids == {"root_e", "mid_e"}

    def test_cycle_does_not_infinite_loop(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "a_e", "entity_key": "a", "alias": "a",
                 "path": "mod_x.py:mod_x.a", "filepath": "mod_x.py"},
                {"value": "b_e", "entity_key": "b", "alias": "b",
                 "path": "mod_x.py:mod_x.b", "filepath": "mod_x.py"},
            ],
            calls_rows=[
                {"entity_id": "a_e", "value": "b", "value_eid": "b_e"},
                {"entity_id": "b_e", "value": "a", "value_eid": "a_e"},
            ],
        )
        graph = build_call_reachability(registry, "a")
        ids = {n["id"] for n in graph["nodes"]}
        assert ids == {"a_e", "b_e"}
        assert {"source": "a_e", "target": "b_e"} in graph["edges"]
        assert {"source": "b_e", "target": "a_e"} in graph["edges"]

    def test_unresolved_call_is_not_followed(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "helper_e", "entity_key": "helper", "alias": "helper",
                 "path": "mod_a.py:mod_a.helper", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                # A None value_eid (no unique entity_ref match) doesn't
                # expand, alongside one that legitimately does resolve --
                # keeping both in the same table avoids an all-null column
                # DuckDB can't infer a type for.
                {"entity_id": "root_e", "value": "os.getcwd", "value_eid": None},
                {"entity_id": "root_e", "value": "helper", "value_eid": "helper_e"},
            ],
        )
        graph = build_call_reachability(registry, "main")
        ids = {n["id"] for n in graph["nodes"]}
        assert ids == {"root_e", "helper_e"}
        assert graph["edges"] == [{"source": "root_e", "target": "helper_e"}]

    def test_same_file_calls_are_kept_unlike_the_collapsed_graph(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "helper_e", "entity_key": "helper", "alias": "helper",
                 "path": "mod_a.py:mod_a.helper", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "helper", "value_eid": "helper_e"},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["edges"] == [{"source": "root_e", "target": "helper_e"}]

    def test_order_edges_connect_consecutive_resolved_call_targets(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "a_e", "entity_key": "call_a", "alias": "call_a",
                 "path": "mod_a.py:mod_a.call_a", "filepath": "mod_a.py"},
                {"value": "b_e", "entity_key": "call_b", "alias": "call_b",
                 "path": "mod_a.py:mod_a.call_b", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                # call_b is called first in source (seq=0), call_a second
                # (seq=1) -- order_edges must follow seq, not the "calls"
                # rows' own order or alphabetical target order.
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 1},
                {"entity_id": "root_e", "value": "call_b", "value_eid": "b_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["order_edges"] == [{"source": "b_e", "target": "a_e"}]

    def test_order_edges_skip_over_an_unresolved_call_in_the_middle(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "a_e", "entity_key": "call_a", "alias": "call_a",
                 "path": "mod_a.py:mod_a.call_a", "filepath": "mod_a.py"},
                {"value": "b_e", "entity_key": "call_b", "alias": "call_b",
                 "path": "mod_a.py:mod_a.call_b", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 0},
                {"entity_id": "root_e", "value": "os.getcwd", "value_eid": None, "seq": 1},
                {"entity_id": "root_e", "value": "call_b", "value_eid": "b_e", "seq": 2},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["order_edges"] == [{"source": "a_e", "target": "b_e"}]

    def test_no_order_edges_from_a_single_call(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "a_e", "entity_key": "call_a", "alias": "call_a",
                 "path": "mod_a.py:mod_a.call_a", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["order_edges"] == []

    def test_order_edges_do_not_cross_between_different_callers(self):
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "a_e", "entity_key": "call_a", "alias": "call_a",
                 "path": "mod_a.py:mod_a.call_a", "filepath": "mod_a.py"},
                {"value": "b_e", "entity_key": "call_b", "alias": "call_b",
                 "path": "mod_a.py:mod_a.call_b", "filepath": "mod_a.py"},
            ],
            calls_rows=[
                # root calls call_a, which itself calls call_b -- two
                # different callers, each with exactly one call of their
                # own, so no "next call" relationship exists between them.
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 0},
                {"entity_id": "a_e", "value": "call_b", "value_eid": "b_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["order_edges"] == []

    def test_root_not_found_raises(self):
        registry = _reachability_registry(entity_id_rows=[
            {"value": "root_e", "entity_key": "main", "alias": "main",
             "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
        ])
        with pytest.raises(ValueError, match="does_not_exist"):
            build_call_reachability(registry, "does_not_exist")

    def test_ambiguous_root_raises(self):
        # No `alias` column -- candidate_entity_ids falls straight through
        # to substring-of-path matching, where "foo" matches both rows.
        registry = _reachability_registry(entity_id_rows=[
            {"value": "a_e", "entity_key": "helper_foo",
             "path": "mod_a.py:mod_a.helper_foo", "filepath": "mod_a.py"},
            {"value": "b_e", "entity_key": "other_foo",
             "path": "mod_b.py:mod_b.other_foo", "filepath": "mod_b.py"},
        ])
        with pytest.raises(ValueError, match="foo"):
            build_call_reachability(registry, "foo")

    def test_call_target_resolved_to_a_non_python_entity_is_not_followed(self):
        """A bare-name call (e.g. the builtin `float(...)`) can coincidentally
        substring/alias-match a YAML-sourced entity (e.g. iacs's own `float`
        schema-type entity in builtins/components.yaml) -- that's never a
        real call, so a target outside a .py file is dropped rather than
        shown as a false-positive node/edge."""
        registry = _reachability_registry(
            entity_id_rows=[
                {"value": "root_e", "entity_key": "main", "alias": "main",
                 "path": "mod_a.py:mod_a.main", "filepath": "mod_a.py"},
                {"value": "yaml_e", "entity_key": "float", "alias": "float",
                 "path": "builtins/components.yaml:base_data_type.float",
                 "filepath": "builtins/components.yaml"},
            ],
            calls_rows=[
                {"entity_id": "root_e", "value": "float", "value_eid": "yaml_e"},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert [n["id"] for n in graph["nodes"]] == ["root_e"]
        assert graph["edges"] == []

    def test_class_method_label_keeps_class_prefix(self):
        registry = _reachability_registry(entity_id_rows=[
            {"value": "root_e", "entity_key": "resolve", "alias": "resolve",
             "path": "story_simulator/resolve.py:story_simulator.resolve.TurnReplay.resolve",
             "filepath": "story_simulator/resolve.py"},
        ])
        graph = build_call_reachability(registry, "root_e")
        assert graph["nodes"][0]["label"] == "TurnReplay.resolve"

    def test_module_entity_label_is_just_the_module_name(self):
        registry = _reachability_registry(entity_id_rows=[
            {"value": "root_e", "entity_key": "core", "alias": "core",
             "path": "story_simulator/core.py:story_simulator.core",
             "filepath": "story_simulator/core.py"},
        ])
        graph = build_call_reachability(registry, "root_e")
        assert graph["nodes"][0]["label"] == "core"


# ---------------------------------------------------------------------------
# render_reachability_mermaid
# ---------------------------------------------------------------------------

class TestRenderReachabilityMermaid:

    def test_empty_graph_renders_placeholder(self):
        out = render_reachability_mermaid({"root": None, "nodes": [], "edges": []})
        assert "flowchart" in out

    def test_groups_nodes_into_one_subgraph_per_file(self):
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "helper_e", "label": "helper", "filepath": "a.py"},
                {"id": "util_e", "label": "util", "filepath": "b.py"},
            ],
            "edges": [
                {"source": "root_e", "target": "helper_e"},
                {"source": "helper_e", "target": "util_e"},
            ],
        }
        out = render_reachability_mermaid(graph)
        assert out.count("subgraph") == 2
        assert '["main"]' in out
        assert '["util"]' in out

    def test_root_node_gets_the_root_class(self):
        graph = {
            "root": "root_e",
            "nodes": [{"id": "root_e", "label": "main", "filepath": "a.py"}],
            "edges": [],
        }
        out = render_reachability_mermaid(graph)
        assert "rootNode" in out

    def test_missing_order_edges_key_renders_fine_with_no_dotted_arrows(self):
        """A hand-built graph dict (e.g. an older test, or a caller that
        never populated order_edges) must not KeyError -- order_edges is
        optional, defaulting to none rendered."""
        graph = {
            "root": "root_e",
            "nodes": [{"id": "root_e", "label": "main", "filepath": "a.py"}],
            "edges": [],
        }
        out = render_reachability_mermaid(graph)
        assert "-.->" not in out

    def test_order_edges_render_as_dotted_arrows(self):
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
                {"id": "b_e", "label": "call_b", "filepath": "a.py"},
            ],
            "edges": [
                {"source": "root_e", "target": "a_e"},
                {"source": "root_e", "target": "b_e"},
            ],
            "order_edges": [{"source": "a_e", "target": "b_e"}],
        }
        out = render_reachability_mermaid(graph)
        assert out.count("-->") == 2
        assert out.count("-.->") == 1
