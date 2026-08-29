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
        assert graph["nodes"] == [{"id": "pkg/mod.py", "label": "pkg/mod"}]
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
        assert {"id": "pkg/a.py", "label": "pkg/a"} in graph["nodes"]
        assert {"id": "pkg/b.py", "label": "pkg/b"} in graph["nodes"]
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
        assert graph["nodes"] == [{"id": "pkg/mod.py", "label": "pkg/mod"}]

    def test_nodes_are_sorted_by_filepath(self):
        registry = _registry(entity_id_rows=[
            {"value": "e1", "entity_key": "z", "filepath": "pkg/z.py"},
            {"value": "e2", "entity_key": "a", "filepath": "pkg/a.py"},
        ])
        graph = build_architecture_graph(registry)
        assert [n["id"] for n in graph["nodes"]] == ["pkg/a.py", "pkg/z.py"]

    def test_same_named_files_in_different_directories_get_distinct_labels(self):
        """Two repos' own conftest.py (or any other same-named file in a
        different directory) must render as distinguishable nodes -- a bare
        module-stem label would collapse both to the identical "conftest",
        indistinguishable in the rendered diagram even though their node
        ids (full filepaths) were never actually the same."""
        registry = _registry(entity_id_rows=[
            {"value": "e1", "entity_key": "conftest", "filepath": "repo_a/tests/conftest.py"},
            {"value": "e2", "entity_key": "conftest", "filepath": "repo_b/tests/conftest.py"},
        ])
        graph = build_architecture_graph(registry)
        labels = {n["label"] for n in graph["nodes"]}
        assert labels == {"repo_a/tests/conftest", "repo_b/tests/conftest"}


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

    def test_call_sequence_targets_follow_seq_not_calls_row_order(self):
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
                # (seq=1) -- the sequence must follow seq, not the "calls"
                # rows' own order or alphabetical target order.
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 1},
                {"entity_id": "root_e", "value": "call_b", "value_eid": "b_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["call_sequences"] == [{"caller": "root_e", "targets": ["b_e", "a_e"]}]

    def test_call_sequence_skips_over_an_unresolved_call_in_the_middle(self):
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
        assert graph["call_sequences"] == [{"caller": "root_e", "targets": ["a_e", "b_e"]}]

    def test_call_sequence_has_a_single_target_for_a_single_call(self):
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
        assert graph["call_sequences"] == [{"caller": "root_e", "targets": ["a_e"]}]

    def test_call_sequences_are_kept_separate_per_caller(self):
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
                # own, so two separate one-target sequences, not one
                # two-target sequence crossing callers.
                {"entity_id": "root_e", "value": "call_a", "value_eid": "a_e", "seq": 0},
                {"entity_id": "a_e", "value": "call_b", "value_eid": "b_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main")
        assert graph["call_sequences"] == [
            {"caller": "root_e", "targets": ["a_e"]},
            {"caller": "a_e", "targets": ["b_e"]},
        ]

    def test_call_sequence_excludes_a_caller_cut_off_by_max_depth(self):
        """mid_e is reached (added to the frontier) but never itself
        expanded once max_depth stops the BFS -- its own call to leaf_e
        must not show up as a call_sequences entry, matching test_max_depth_
        limits_traversal's existing "no edge for it either" behavior."""
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
                {"entity_id": "root_e", "value": "helper", "value_eid": "mid_e", "seq": 0},
                {"entity_id": "mid_e", "value": "util", "value_eid": "leaf_e", "seq": 0},
            ],
        )
        graph = build_call_reachability(registry, "main", max_depth=1)
        assert graph["call_sequences"] == [{"caller": "root_e", "targets": ["mid_e"]}]

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

    def test_uses_default_theme_no_init_directive(self):
        """No `%%{init: ...}%%` override -- plain default Mermaid theme.

        A transparent-cluster-background override was tried here at one
        point while tracking down a boundary-crossing-edge rendering bug
        (see `render_reachability_mermaid`'s own docstring for the actual
        root cause and fix), but wasn't needed for correctness once that
        bug was actually fixed, so it's gone: the diagram's first line is
        the `flowchart` declaration itself, nothing before it."""
        graph = {
            "root": "root_e",
            "nodes": [{"id": "root_e", "label": "main", "filepath": "a.py"}],
            "edges": [],
        }
        out = render_reachability_mermaid(graph)
        lines = out.splitlines()
        assert lines[0].startswith("flowchart")
        assert "%%{init:" not in out

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

    def test_missing_call_sequences_key_falls_back_to_plain_edges(self):
        """A hand-built graph dict (e.g. an older test, or a caller that
        never populated call_sequences) must not KeyError -- it falls back
        to one plain arrow per edges entry, no subgraph, no dotted arrows."""
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
            ],
            "edges": [{"source": "root_e", "target": "a_e"}],
        }
        out = render_reachability_mermaid(graph)
        assert out.count("-->") == 1
        assert "-.->" not in out

    def test_single_target_call_sequence_uses_a_plain_arrow_no_subgraph(self):
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
            ],
            "edges": [{"source": "root_e", "target": "a_e"}],
            "call_sequences": [{"caller": "root_e", "targets": ["a_e"]}],
        }
        out = render_reachability_mermaid(graph)
        assert out.count("-->") == 1
        assert "-.->" not in out
        assert "seq0" not in out

    def test_multi_target_call_sequence_becomes_a_subgraph_with_one_incoming_arrow(self):
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
            "call_sequences": [{"caller": "root_e", "targets": ["a_e", "b_e"]}],
        }
        out = render_reachability_mermaid(graph)
        # One solid arrow: root -> the sequence subgraph (not two, one per
        # target) -- plus the one dotted arrow chaining a_e to b_e inside it.
        assert out.count("-->") == 1
        assert out.count("-.->") == 1
        assert "subgraph seq0" in out
        # a_e/b_e are declared inside the sequence subgraph, not root's
        # file subgraph -- so there's exactly one subgraph total besides
        # the sequence one (root's own file subgraph).
        assert out.count("subgraph") == 2

    def test_sequence_subgraph_declares_no_explicit_inner_direction(self):
        """A seqN subgraph must never emit its own `direction` line.

        Confirmed via a minimal repro (a multi-node chain in a box, with
        the box's first member also targeted by an edge from outside):
        Mermaid/dagre's compound layout mis-anchors an edge crossing a
        subgraph boundary whenever that subgraph declares an explicit
        inner `direction`, matching or not -- the edge renders as if it
        started from an arbitrary internal node instead of the true
        source. Omitting the inner direction line (so the box inherits the
        outer flowchart's direction implicitly) is the only combination
        that both avoids the bug and keeps the box's chain legible."""
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
            "call_sequences": [{"caller": "root_e", "targets": ["a_e", "b_e"]}],
        }
        out = render_reachability_mermaid(graph)
        assert "direction TB" not in out
        assert "direction LR" not in out

    def test_call_sequence_members_are_pulled_out_of_the_file_subgraph(self):
        """A node inside a seqN subgraph must not also be declared in its
        file subgraph -- Mermaid doesn't support a node in two containers,
        and it would be visually redundant either way."""
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
            "call_sequences": [{"caller": "root_e", "targets": ["a_e", "b_e"]}],
        }
        out = render_reachability_mermaid(graph)
        assert out.count('["call_a"]') == 1
        assert out.count('["call_b"]') == 1

    def test_outgoing_edge_from_a_sequence_member_still_originates_at_its_own_node(self):
        """a_e is a member of root_e's box, but a_e itself also calls d_e
        (a single, unrelated call elsewhere) -- that edge must still be
        drawn from a_e specifically, not from the box's boundary. Only
        *incoming* edges get the box treatment; which member actually made
        an outgoing call stays visible rather than collapsing into "the
        box, generically" (see test_incoming_edge_to_a_sequence_member_
        terminates_at_its_box for the target-side counterpart)."""
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
                {"id": "b_e", "label": "call_b", "filepath": "a.py"},
                {"id": "d_e", "label": "call_d", "filepath": "a.py"},
            ],
            "edges": [
                {"source": "root_e", "target": "a_e"},
                {"source": "root_e", "target": "b_e"},
                {"source": "a_e", "target": "d_e"},
            ],
            "call_sequences": [
                {"caller": "root_e", "targets": ["a_e", "b_e"]},
                {"caller": "a_e", "targets": ["d_e"]},
            ],
        }
        out = render_reachability_mermaid(graph)
        assert "n1 --> n3" in out
        assert "seq0 --> n3" not in out

    def test_incoming_edge_to_a_sequence_member_terminates_at_its_box(self):
        """d_e is a plain caller of a single target, b_e -- but b_e is
        itself a member of root_e's own box, so the edge must land on that
        box's boundary, not on b_e specifically."""
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
                {"id": "b_e", "label": "call_b", "filepath": "a.py"},
                {"id": "d_e", "label": "call_d", "filepath": "a.py"},
            ],
            "edges": [
                {"source": "root_e", "target": "a_e"},
                {"source": "root_e", "target": "b_e"},
                {"source": "d_e", "target": "b_e"},
            ],
            "call_sequences": [
                {"caller": "root_e", "targets": ["a_e", "b_e"]},
                {"caller": "d_e", "targets": ["b_e"]},
            ],
        }
        out = render_reachability_mermaid(graph)
        assert "n3 --> seq0" in out

    def test_two_different_members_calling_the_same_target_both_render(self):
        """a_e and c_e are two different members of root_e's box, and each
        separately calls the same d_e -- since the source side is never
        abstracted, these are genuinely distinct (n1, n4)/(n3, n4) pairs,
        not duplicates of each other, and both arrows must show: knowing
        *which* member reached d_e is exactly the information source-side
        abstraction would have thrown away."""
        graph = {
            "root": "root_e",
            "nodes": [
                {"id": "root_e", "label": "main", "filepath": "a.py"},
                {"id": "a_e", "label": "call_a", "filepath": "a.py"},
                {"id": "b_e", "label": "call_b", "filepath": "a.py"},
                {"id": "c_e", "label": "call_c", "filepath": "a.py"},
                {"id": "d_e", "label": "call_d", "filepath": "a.py"},
            ],
            "edges": [
                {"source": "root_e", "target": "a_e"},
                {"source": "root_e", "target": "b_e"},
                {"source": "root_e", "target": "c_e"},
                {"source": "a_e", "target": "d_e"},
                {"source": "c_e", "target": "d_e"},
            ],
            "call_sequences": [
                {"caller": "root_e", "targets": ["a_e", "b_e", "c_e"]},
                {"caller": "a_e", "targets": ["d_e"]},
                {"caller": "c_e", "targets": ["d_e"]},
            ],
        }
        out = render_reachability_mermaid(graph)
        assert "n1 --> n4" in out
        assert "n3 --> n4" in out
