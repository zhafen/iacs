#!/usr/bin/env python3
"""Generate an HTML report of the "leaf" requirements under a given root
entity in an iacs manifest -- the deepest requirements in an alternating
requirement/solution tree, the ones with no further nested requirement
anywhere beneath them (only candidate solutions). Those are the
requirements that actually need a decision made now; everything above
them in the tree is just the reasoning chain that led here.

For each leaf requirement found, lists every candidate solution nested
under it (or cross-linked to it via `solution of:`), with its
description and pros/cons/cost/code_example if present -- the same
per-solution detail generate_live_testing_report.py (story-simulator)
uses, ported here since the underlying tree shape (bare `requirement`/
`solution` tags, resolved via emc2p's parent_from_hierarchy +
components_with_resolved_paths) is identical.

Generic over the root: pass any entity key (or unique path substring)
via --root and this walks whatever alternating tree hangs off it,
rather than assuming one fixed subtree the way the story-simulator
script does.

Run: uv run python scripts/generate_leaf_requirements_report.py --root <entity_key> [--manifest DIR ...] [--output PATH] [--fragment]
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from iacs.commands import make_registrar, parse_manifest_env

DEFAULT_OUTPUT = Path("/tmp/leaf_requirements_report.html")


def load_subtree(registrar, root_key: str) -> dict:
    """Node/edge data for the alternating requirement/solution tree rooted
    at any entity whose key or path contains ``root_key`` -- same
    resolution approach as story-simulator's generate_live_testing_report.py
    (parent_from_hierarchy + components_with_resolved_paths), generalized
    to an arbitrary root instead of one hardcoded entity.
    """
    from emc2p.dataflows.derive.resolve_paths import (
        components_with_resolved_paths,
        fields_of_type_entity_ref,
        parent_from_hierarchy,
    )

    entity_id = registrar.get("entity_id")
    field = registrar.get("field")
    components = registrar._registry._components
    hierarchy = parent_from_hierarchy(entity_id)
    resolved = components_with_resolved_paths(
        entity_id=entity_id,
        components=components,
        fields_of_type_entity_ref=fields_of_type_entity_ref(entity_id, field),
        parent_from_hierarchy=hierarchy,
    )

    eids = entity_id.execute()
    path_of = dict(zip(eids["value"].astype(str), eids["path"].astype(str)))

    def clean(path: str) -> str:
        return path.split(":", 1)[1]

    def in_subtree(path: str) -> bool:
        # Segment-exact match, not substring: root_key must be one full
        # dot-separated path component, not just text that happens to
        # appear inside a longer, unrelated segment. A plain substring
        # marker (e.g. "f'.{root_key}'") misses a truly top-level root
        # (no leading dot before its own first segment) -- exercised by
        # concise_inline_comments, itself a root with no parent.
        return root_key in path.split(".")

    subtree_path_of = {
        eid: clean(p)
        for eid, p in path_of.items()
        if in_subtree(clean(p))
    }
    path_to_eid = {p: eid for eid, p in subtree_path_of.items()}

    descriptions: dict[str, str] = {}
    for _, row in registrar.get("description").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            descriptions[eid] = str(row["value"])

    types: dict[str, str] = {}
    for ctype in ("requirement", "solution"):
        for _, row in registrar.get(ctype).execute().iterrows():
            eid = str(row["entity_id"])
            if eid in subtree_path_of:
                types[eid] = ctype

    nodes = []
    parent_of: dict[str, str | None] = {}
    for eid, path in subtree_path_of.items():
        parent_path = path.rsplit(".", 1)[0] if "." in path else None
        parent_id = path_to_eid.get(parent_path) if parent_path else None
        parent_of[eid] = parent_id
        key = path.rsplit(".", 1)[-1]
        nodes.append({
            "id": eid,
            "key": key,
            "label": key.replace("_", " "),
            "type": types.get(eid),
            "description": descriptions.get(eid, ""),
            "parent_id": parent_id,
        })

    cross_edges: list[tuple[str, str]] = []
    seen_cross = set()
    for ctype in ("requirement", "solution"):
        df = resolved[ctype].to_pandas()
        for _, row in df.iterrows():
            eid = str(row["entity_id"])
            if eid not in subtree_path_of:
                continue
            target = row.get("value_eid")
            if target is None or (isinstance(target, float) and target != target):
                continue
            target = str(target)
            if target not in subtree_path_of or target == parent_of.get(eid):
                continue
            pair = (eid, target)
            if pair not in seen_cross:
                seen_cross.add(pair)
                cross_edges.append(pair)

    costs: dict[str, list[tuple[str, float]]] = {}
    for _, row in registrar.get("cost").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            costs.setdefault(eid, []).append((str(row["type"]), float(row["value"])))

    pros_cons: dict[str, list[dict]] = {}
    for sign in ("pro", "con"):
        for _, row in registrar.get(sign).execute().iterrows():
            eid = str(row["entity_id"])
            if eid in subtree_path_of:
                pros_cons.setdefault(eid, []).append({"sign": sign, "note": str(row["value"])})

    return {
        "nodes": nodes,
        "cross_edges": cross_edges,
        "costs": costs,
        "pros_cons": pros_cons,
    }


def find_leaf_requirements(subtree: dict) -> list[dict]:
    """Requirement-type nodes with no requirement anywhere in their own
    descendant tree (walking through any nested solutions) -- the
    deepest, currently-undecided requirements, as opposed to ones whose
    resolution is deferred to a nested sub-requirement further down."""
    nodes = subtree["nodes"]
    by_id = {n["id"]: n for n in nodes}
    children_of: dict[str, list[str]] = {}
    for n in nodes:
        if n["parent_id"]:
            children_of.setdefault(n["parent_id"], []).append(n["id"])
    for from_id, to_id in subtree["cross_edges"]:
        if by_id[from_id]["type"] == "solution" and by_id[to_id]["type"] == "requirement":
            children_of.setdefault(to_id, [])  # cross-links don't add descendants of a requirement

    def has_requirement_descendant(node_id: str) -> bool:
        for child_id in children_of.get(node_id, []):
            if by_id[child_id]["type"] == "requirement":
                return True
            if has_requirement_descendant(child_id):
                return True
        return False

    return [
        n for n in nodes
        if n["type"] == "requirement" and not has_requirement_descendant(n["id"])
    ]


def _solutions_of(requirement_id: str, subtree: dict) -> list[dict]:
    by_id = {n["id"]: n for n in subtree["nodes"]}
    solution_ids = [
        n["id"] for n in subtree["nodes"]
        if n["type"] == "solution" and n["parent_id"] == requirement_id
    ]
    for from_id, to_id in subtree["cross_edges"]:
        if to_id == requirement_id and by_id.get(from_id, {}).get("type") == "solution":
            if from_id not in solution_ids:
                solution_ids.append(from_id)
    return [by_id[sid] for sid in sorted(solution_ids, key=lambda i: by_id[i]["key"])]


def _render_solution(node: dict, subtree: dict) -> str:
    description = html.escape(node["description"])
    cost_items = subtree["costs"].get(node["id"], [])
    cost_html = (
        ", ".join(f"{value:g} {ctype}" for ctype, value in cost_items) if cost_items else "none"
    )
    items = subtree["pros_cons"].get(node["id"], [])
    ratings_html = "".join(
        f"""
        <li class="rating rating-{item['sign']}">
          <span class="sign-badge sign-{item['sign']}">{'Pro' if item['sign'] == 'pro' else 'Con'}</span>
          <p class="rating-note">{html.escape(item['note'])}</p>
        </li>"""
        for item in items
    )
    return f"""
      <details class="solution">
        <summary>
          <span class="solution-name">{html.escape(node['label'])}</span>
          <span class="cost">cost: {html.escape(cost_html)}</span>
        </summary>
        <div class="solution-body">
          <p class="solution-description">{description}</p>
          <ul class="ratings">{ratings_html}</ul>
        </div>
      </details>"""


def _render_leaf_requirement(node: dict, subtree: dict) -> str:
    description = html.escape(node["description"])
    solutions = _solutions_of(node["id"], subtree)
    solutions_html = (
        "".join(_render_solution(s, subtree) for s in solutions)
        or '<p class="no-solutions">No candidate solution currently recorded.</p>'
    )
    return f"""
  <section class="requirement">
    <p class="eyebrow">Requirement (leaf)</p>
    <h2>{html.escape(node['label'])}</h2>
    <p class="requirement-description">{description}</p>
    {solutions_html}
  </section>"""


_STYLE = """
  :root {
    color-scheme: light dark;
    --bg: #f7f6f2; --surface: #ffffff; --border: #e2ded2;
    --fg: #1e211d; --muted: #6b6f63; --muted-2: #8a8d80;
    --accent: #0f6e67; --accent-fg: #ffffff;
    --pro: #2e6b45; --pro-bg: #e4f1e7;
    --con: #a3392c; --con-bg: #f8e9e5;
    --chip-bg: #ece9dd; --chip-fg: #55584c;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #161816; --surface: #1e211d; --border: #33362e;
      --fg: #eae8de; --muted: #a3a695; --muted-2: #7d8071;
      --accent: #4fb8ae; --accent-fg: #0d1513;
      --pro: #7bc794; --pro-bg: #1c2e21;
      --con: #e08b7c; --con-bg: #34211d;
      --chip-bg: #2a2d26; --chip-fg: #b9bcae;
    }
  }
  :root[data-theme="dark"] {
    --bg: #161816; --surface: #1e211d; --border: #33362e;
    --fg: #eae8de; --muted: #a3a695; --muted-2: #7d8071;
    --accent: #4fb8ae; --accent-fg: #0d1513;
    --pro: #7bc794; --pro-bg: #1c2e21;
    --con: #e08b7c; --con-bg: #34211d;
    --chip-bg: #2a2d26; --chip-fg: #b9bcae;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--fg);
    font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 760px; margin: 0 auto; padding: 3rem 1.5rem 5rem;
    line-height: 1.55;
  }
  .masthead { margin-bottom: 2.75rem; }
  .kicker {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 0.6rem;
  }
  h1 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.7rem; font-weight: 600; margin: 0 0 0.6rem;
  }
  .subtitle { color: var(--muted); margin: 0; font-size: 0.95rem; max-width: 62ch; }
  .requirement { margin-bottom: 2.75rem; }
  .eyebrow {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 0.3rem;
  }
  .requirement h2 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.25rem; font-weight: 600; margin: 0 0 0.5rem;
  }
  .requirement-description { color: var(--muted); margin: 0 0 0.9rem; max-width: 62ch; }
  .no-solutions { color: var(--muted-2); font-style: italic; }
  details.solution {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    margin: 0.7rem 0; padding: 0 1.1rem;
  }
  details.solution summary {
    cursor: pointer; padding: 0.85rem 0; display: flex; align-items: center;
    gap: 0.7rem; list-style: none; font-weight: 600;
  }
  details.solution summary::-webkit-details-marker { display: none; }
  details.solution summary::before {
    content: "▸"; color: var(--muted-2); font-weight: normal; flex-shrink: 0;
    transition: transform 0.15s ease;
  }
  details.solution[open] summary::before { transform: rotate(90deg); }
  .solution-name { flex: 1; font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.95rem; }
  .cost {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums; font-size: 0.78rem; color: var(--muted);
  }
  .solution-body { padding: 0 0 1.1rem 1.5rem; }
  .solution-description { color: var(--fg); margin-top: 0; }
  ul.ratings { list-style: none; margin: 0.6rem 0 0; padding: 0; }
  li.rating { padding: 0.6rem 0; border-top: 1px solid var(--border); display: flex; gap: 0.55rem; align-items: baseline; }
  li.rating:first-child { border-top: none; }
  .sign-badge {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.66rem; font-weight: 600; letter-spacing: 0.04em;
    padding: 0.12rem 0.5rem; border-radius: 5px; flex-shrink: 0;
  }
  .sign-pro { background: var(--pro-bg); color: var(--pro); }
  .sign-con { background: var(--con-bg); color: var(--con); }
  .rating-note { margin: 0; color: var(--muted); font-size: 0.92rem; max-width: 62ch; }
"""

_TITLE = "Leaf Requirements"


def render_report(root_key: str, leaves: list[dict], subtree: dict, fragment: bool) -> str:
    sections = "".join(_render_leaf_requirement(n, subtree) for n in leaves) or (
        '<p class="no-solutions">No leaf requirements found under this root.</p>'
    )
    body = f"""
  <div class="masthead">
    <p class="kicker">{html.escape(root_key)} &middot; leaf requirements</p>
    <h1>Leaf Requirements</h1>
    <p class="subtitle">
      The deepest requirements under {html.escape(root_key)} -- the ones
      with no further nested requirement, only candidate solutions still
      to choose between.
    </p>
  </div>
  {sections}"""
    if fragment:
        return f'<title>{html.escape(_TITLE)}</title>\n<style>{_STYLE}</style>\n{body}\n'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(_TITLE)}</title>
<style>{_STYLE}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Entity key (or unique path substring) to scope the search to.")
    parser.add_argument("--manifest", nargs="*", default=None, help="Manifest dirs; defaults to IACS_MANIFEST env / built-in default.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--fragment", action="store_true",
        help="Write title/style/body content only, for publishing as a Claude Artifact.",
    )
    args = parser.parse_args()

    manifest_paths = args.manifest if args.manifest else parse_manifest_env()
    registrar = make_registrar(manifest_paths)
    subtree = load_subtree(registrar, args.root)
    leaves = find_leaf_requirements(subtree)
    content = render_report(args.root, leaves, subtree, args.fragment)
    args.output.write_text(content)
    print(f"Wrote {args.output} ({len(leaves)} leaf requirement(s) found)")


if __name__ == "__main__":
    main()
