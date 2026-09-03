"""Pixel/geometry-level regression test for the sequence-subgraph edge-anchoring bug.

Companion to ``TestRenderReachabilityMermaid::
test_sequence_subgraph_declares_no_explicit_inner_direction`` in
``test_architecture_graph.py``, which guards the *source* of the bug (an
explicit inner ``direction`` line on a ``seqN`` subgraph) with a cheap
string check. That's enough to stop this exact regression from
recurring, but it can't catch a *different* change that reintroduces the
same visual symptom by some other means -- only actually rendering the
diagram and inspecting where Mermaid/dagre put the edge can do that. This
module does the actual rendering.

An outgoing edge from a sequence-box member to a node outside the box
mis-anchors under Mermaid/dagre's compound layout whenever the subgraph
declares any explicit inner ``direction`` line, even one that matches
the outer direction -- the edge appears to originate from an arbitrary
other node in the box instead of its true source.
``render_reachability_mermaid`` avoids this by never emitting an inner
``direction`` line at all.
"""

import re
import shutil
import subprocess

import pytest

from iacs.views.architecture_graph import render_reachability_mermaid

MMDC_AVAILABLE = shutil.which("npx") is not None


def _render_svg(mermaid_text: str, tmp_path) -> str:
    """Render Mermaid source to SVG text via ``@mermaid-js/mermaid-cli``.

    Skips the test (rather than failing it) if ``npx`` can't fetch/run
    mermaid-cli -- this test verifies real browser-rendered layout, which
    isn't available in every environment (e.g. no network to fetch the
    npm package), and that's a reason to skip, not to report a false
    positive bug.
    """
    mmd_path = tmp_path / "diagram.mmd"
    svg_path = tmp_path / "diagram.svg"
    puppeteer_config = tmp_path / "puppeteer-config.json"
    mmd_path.write_text(mermaid_text, encoding="utf-8")
    puppeteer_config.write_text(
        '{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}', encoding="utf-8"
    )
    try:
        subprocess.run(
            [
                "npx", "-y", "@mermaid-js/mermaid-cli",
                "-i", str(mmd_path), "-o", str(svg_path),
                "-p", str(puppeteer_config),
            ],
            capture_output=True, text=True, timeout=120, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        pytest.skip(f"mermaid-cli unavailable or failed to render: {exc}")
    return svg_path.read_text(encoding="utf-8")


def _node_center(svg_text: str, node_id: str) -> tuple[float, float]:
    """Return the (x, y) center mermaid placed a flowchart node at.

    Mermaid CLI's default SVG id prefix is ``my-svg``; a node's group
    element id is ``{prefix}-flowchart-{node_id}-{index}`` and its
    ``transform="translate(x, y)"`` gives the node's center. Attribute
    order on the ``<g>`` tag isn't assumed fixed, same reasoning as
    ``_edge_start_point``.
    """
    tag_match = re.search(
        rf'<g\b[^>]*id="my-svg-flowchart-{re.escape(node_id)}-\d+"[^>]*>',
        svg_text,
    )
    assert tag_match, f"could not find node {node_id!r} in rendered SVG"
    transform_match = re.search(
        r'transform="translate\(([-\d.]+),\s*([-\d.]+)\)"', tag_match.group(0)
    )
    assert transform_match, f"node {node_id!r} tag has no translate transform"
    return float(transform_match.group(1)), float(transform_match.group(2))


def _edge_start_point(svg_text: str, source_id: str, target_id: str) -> tuple[float, float]:
    """Return the (x, y) coordinate mermaid drew an edge's path starting from.

    An edge path element's id is ``{prefix}-L_{source}_{target}_{index}``
    and its ``d`` attribute starts with an absolute moveto (``M x,y``) at
    the point the edge line actually begins on screen. Attribute order on
    the ``<path>`` tag isn't guaranteed (``d`` can come before or after
    ``id``), so the whole tag is matched first and ``d`` extracted from
    within it, rather than assuming a fixed order.
    """
    tag_match = re.search(
        rf'<path\b[^>]*id="my-svg-L_{re.escape(source_id)}_{re.escape(target_id)}_\d+"[^>]*>',
        svg_text,
    )
    assert tag_match, f"could not find edge {source_id}->{target_id} in rendered SVG"
    d_match = re.search(r'd="([^"]+)"', tag_match.group(0))
    assert d_match, f"path tag for edge {source_id}->{target_id} has no d attribute"
    move_match = re.match(r"M\s*([-\d.]+)[,\s]+([-\d.]+)", d_match.group(1))
    assert move_match, f"could not parse path data for edge {source_id}->{target_id}"
    return float(move_match.group(1)), float(move_match.group(2))


def _distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


@pytest.mark.skipif(not MMDC_AVAILABLE, reason="npx not available to run mermaid-cli")
def test_outgoing_edge_from_sequence_member_renders_from_that_node_not_a_sibling(tmp_path):
    """Render a repro shape and check the *actual rendered pixel geometry*.

    root_e calls a_e, b_e, and e_e (3 targets -> they become one seqN box,
    chained a_e -.-> b_e -.-> e_e); a_e -- the box's *first* member -- also
    calls c_e outside the box. A 2-member box wasn't enough to distinguish
    the bug from the fix here (with only two members, "the box's exit
    point" and "the true source" can coincide by chance); this needed a
    3+-member box with the true source *not* at the exit end to actually
    separate the two hypotheses -- confirmed by hand against both the
    buggy and fixed renderer during this test's development, where the
    buggy version anchored the edge at a fixed point near e_e (the box's
    *last*, exit-adjacent member) regardless of which member the edge's
    source actually was.

    This renders the real diagram and asserts the a_e->c_e edge's drawn
    starting point is closer to a_e's node than to e_e's -- the thing a
    string-level check on the generated Mermaid source can't see, since
    the bug is purely about where dagre lays the edge out, not about what
    the source text says.
    """
    graph = {
        "root": "root_e",
        "nodes": [
            {"id": "root_e", "label": "root", "filepath": "a.py"},
            {"id": "a_e", "label": "A", "filepath": "a.py"},
            {"id": "b_e", "label": "B", "filepath": "a.py"},
            {"id": "e_e", "label": "E", "filepath": "a.py"},
            {"id": "c_e", "label": "C", "filepath": "a.py"},
        ],
        "edges": [
            {"source": "root_e", "target": "a_e"},
            {"source": "root_e", "target": "b_e"},
            {"source": "root_e", "target": "e_e"},
            {"source": "a_e", "target": "c_e"},
        ],
        "call_sequences": [
            {"caller": "root_e", "targets": ["a_e", "b_e", "e_e"]},
            {"caller": "a_e", "targets": ["c_e"]},
        ],
    }
    mermaid_text = render_reachability_mermaid(graph)
    id_map = {"root_e": "n0", "a_e": "n1", "b_e": "n2", "e_e": "n3", "c_e": "n4"}
    assert f'{id_map["a_e"]} --> {id_map["c_e"]}' in mermaid_text

    svg_text = _render_svg(mermaid_text, tmp_path)
    a_center = _node_center(svg_text, id_map["a_e"])
    e_center = _node_center(svg_text, id_map["e_e"])
    edge_start = _edge_start_point(svg_text, id_map["a_e"], id_map["c_e"])

    assert _distance(edge_start, a_center) < _distance(edge_start, e_center), (
        f"A->C edge starts at {edge_start}, which is closer to E {e_center} "
        f"than to A {a_center} -- the edge is mis-anchored to the box's "
        "exit end instead of its true source member (the dagre inner-"
        "direction bug)."
    )
