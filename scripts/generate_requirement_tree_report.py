#!/usr/bin/env python3
"""Generate an HTML report of the alternating requirement/solution tree
rooted at a given entity in an iacs manifest.

Renders the same kind of document story-simulator's
generate_live_testing_report.py produces for its
human_validated_test_framework tree: a table of contents (section
headers only, linking down the page), one full section per requirement
(description + every candidate solution nested under it or cross-linked
to it via `solution of:`, each with its own description/pros/cons/cost/
code_example), then a solution-first "Solutions" index split into
Selected/Unselected. If the root has a direct child literally named
`dependencies`, a "Dependencies" section is appended too (see
story-simulator's own dependencies: subtree for the convention this
follows); otherwise that section is simply omitted.

Generic over the root: pass any entity key (or unique path segment) via
--root and this walks whatever alternating tree hangs off it, rather
than assuming one fixed subtree. The root entity's own name is shown in
both the page title and a masthead at the top of the document, so it's
never ambiguous which tree a given report was generated from.

Run: uv run python scripts/generate_requirement_tree_report.py --root <entity_key> [--manifest DIR ...] [--output PATH] [--fragment]
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from iacs.commands import make_registrar, parse_manifest_env

DEFAULT_OUTPUT = Path("/tmp/requirement_tree_report.html")

DEPENDENCIES_KEY = "dependencies"


def _clean(path: str) -> str:
    return path.split(":", 1)[1]


def load_subtree(registrar, root_key: str) -> dict:
    """Node/edge data for the alternating requirement/solution tree rooted
    at the entity whose key is exactly ``root_key`` -- same resolution
    approach as story-simulator's generate_live_testing_report.py
    (parent_from_hierarchy + components_with_resolved_paths), generalized
    to an arbitrary root instead of one hardcoded entity.

    Excludes any ``dependencies`` child of the root (and its own
    descendants) from the main node set -- those are implementation
    entities, not requirements/solutions, and are collected separately by
    load_dependencies_data so they don't leak in as bogus requirement-
    typed nodes (see story-simulator's own DEPENDENCIES_MARKER exclusion,
    which this mirrors).
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

    def in_subtree(path: str) -> bool:
        # Segment-exact match, not substring: root_key must be one full
        # dot-separated path component. A plain substring marker misses a
        # truly top-level root (no leading dot before its own first
        # segment).
        return root_key in path.split(".")

    def under_dependencies(path: str) -> bool:
        segments = path.split(".")
        return root_key in segments and DEPENDENCIES_KEY in segments[segments.index(root_key) + 1:]

    subtree_path_of = {
        eid: _clean(p)
        for eid, p in path_of.items()
        if in_subtree(_clean(p)) and not under_dependencies(_clean(p))
    }
    path_to_eid = {p: eid for eid, p in subtree_path_of.items()}

    descriptions: dict[str, str] = {}
    for _, row in registrar.get("description").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            descriptions[eid] = str(row["value"])

    work_states: dict[str, str] = {}
    for _, row in registrar.get("work_state").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            work_states[eid] = str(row["value"])

    selected: dict[str, bool] = {}
    for _, row in registrar.get("selected").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            selected[eid] = bool(row["value"])

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
            "work_state": work_states.get(eid, "unknown"),
            "selected": selected.get(eid, False),
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

    code_examples: dict[str, dict] = {}
    for _, row in registrar.get("code_example").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            code_examples[eid] = {"language": str(row["language"]), "code": str(row["value"])}

    return {
        "nodes": nodes,
        "cross_edges": cross_edges,
        "costs": costs,
        "pros_cons": pros_cons,
        "code_examples": code_examples,
    }


def load_dependencies_data(registrar, root_key: str) -> dict | None:
    """Implementation entities under root_key.dependencies, if that child
    exists -- same shape/convention as story-simulator's own
    dependencies: subtree. Returns None (no Dependencies section) if the
    root has no such child."""
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

    container_prefix = f"{root_key}.{DEPENDENCIES_KEY}."
    entity_keys: dict[str, str] = {}
    for eid, p in path_of.items():
        cp = _clean(p)
        idx = cp.find(container_prefix)
        if idx == -1:
            continue
        rest = cp[idx + len(container_prefix):]
        if "." in rest:
            continue  # only direct children of dependencies:, not further-nested entities
        entity_keys[eid] = rest

    if not entity_keys:
        return None

    descriptions: dict[str, str] = {}
    for _, row in registrar.get("description").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in entity_keys:
            descriptions[entity_keys[eid]] = str(row["value"])

    work_states: dict[str, str] = {}
    for _, row in registrar.get("work_state").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in entity_keys:
            work_states[entity_keys[eid]] = str(row["value"])

    locations: dict[str, str] = {}
    for _, row in registrar.get("location").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in entity_keys:
            locations[entity_keys[eid]] = str(row["value"])

    entities = {
        key: {
            "description": descriptions.get(key, ""),
            "work_state": work_states.get(key, "unknown"),
            "location": locations.get(key, key),
        }
        for key in entity_keys.values()
    }

    def short_key(eid: str) -> str:
        return _clean(path_of[eid]).rsplit(".", 1)[-1]

    dependency_to_solutions: dict[str, list[str]] = {}
    dep_df = resolved.get("dependence")
    if dep_df is not None:
        for _, row in dep_df.to_pandas().iterrows():
            src_eid = str(row["entity_id"])
            tgt_eid = row.get("value_eid")
            if tgt_eid is None or (isinstance(tgt_eid, float) and tgt_eid != tgt_eid):
                continue
            tgt_eid = str(tgt_eid)
            if tgt_eid not in entity_keys or src_eid not in path_of:
                continue
            dep_key = entity_keys[tgt_eid]
            sol_key = short_key(src_eid)
            dependency_to_solutions.setdefault(dep_key, [])
            if sol_key not in dependency_to_solutions[dep_key]:
                dependency_to_solutions[dep_key].append(sol_key)
    for k in dependency_to_solutions:
        dependency_to_solutions[k].sort()

    return {"entities": entities, "dependency_to_solutions": dependency_to_solutions}


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


def _requirements_of(solution_id: str, subtree: dict) -> list[dict]:
    by_id = {n["id"]: n for n in subtree["nodes"]}
    req_ids = [
        n["id"] for n in subtree["nodes"]
        if n["type"] == "requirement" and n["parent_id"] == solution_id
    ]
    for from_id, to_id in subtree["cross_edges"]:
        if from_id == solution_id and by_id.get(to_id, {}).get("type") == "requirement":
            if to_id not in req_ids:
                req_ids.append(to_id)
    return [by_id[rid] for rid in sorted(req_ids, key=lambda i: by_id[i]["key"])]


def _render_pro_con(item: dict) -> str:
    sign_label = "Pro" if item["sign"] == "pro" else "Con"
    return f"""
        <li class="rating rating-{sign_label.lower()}">
          <span class="sign-badge sign-{sign_label.lower()}">{sign_label}</span>
          <p class="rating-note">{html.escape(item['note'])}</p>
        </li>"""


def _render_solution(node: dict, subtree: dict, show_requirements: bool = False) -> str:
    description = html.escape(node["description"])
    cost_items = subtree["costs"].get(node["id"], [])
    cost_html = (
        ", ".join(f"{value:g} {ctype}" for ctype, value in cost_items) if cost_items else "none"
    )
    items = subtree["pros_cons"].get(node["id"], [])
    pros = [r for r in items if r["sign"] == "pro"]
    cons = [r for r in items if r["sign"] == "con"]
    ratings_html = "".join(_render_pro_con(r) for r in pros + cons)
    requirements_html = ""
    if show_requirements:
        req_nodes = _requirements_of(node["id"], subtree)
        chips = "".join(
            f'<span class="req-chip">{html.escape(r["label"])}</span>' for r in req_nodes
        ) or '<span class="req-chip req-chip-none">none currently</span>'
        requirements_html = f"""
          <p class="section-label">Solves</p>
          <div class="req-chips">{chips}</div>"""
    code_example_html = ""
    example = subtree["code_examples"].get(node["id"])
    if example:
        code_example_html = f"""
          <p class="section-label">Example</p>
          <pre class="code-example"><code class="language-{html.escape(example['language'])}">{html.escape(example['code'])}</code></pre>"""
    selected_class = " solution-selected" if node["selected"] else ""
    selected_badge = '<span class="selected-badge">Selected</span>' if node["selected"] else ""
    return f"""
      <details class="solution{selected_class}">
        <summary>
          {selected_badge}
          <span class="solution-name">{html.escape(node['label'])}</span>
          <span class="work-state work-state-{html.escape(node['work_state'].replace(' ', '-'))}">{html.escape(node['work_state'])}</span>
          <span class="cost">cost: {html.escape(cost_html)}</span>
        </summary>
        <div class="solution-body">
          <p class="solution-description">{description}</p>
          {requirements_html}
          {code_example_html}
          <ul class="ratings">{ratings_html}</ul>
        </div>
      </details>"""


def _requirement_anchor(key: str) -> str:
    return f"req-{key}"


def _render_requirement(node: dict, subtree: dict) -> str:
    description = html.escape(node["description"])
    solutions = _solutions_of(node["id"], subtree)
    solutions_html = (
        "".join(_render_solution(s, subtree) for s in solutions)
        or '<p class="no-solutions">No candidate solution currently recorded.</p>'
    )
    return f"""
  <section class="requirement" id="{_requirement_anchor(node['key'])}">
    <p class="eyebrow">Requirement</p>
    <h2>{html.escape(node['label'])}</h2>
    <p class="requirement-description">{description}</p>
    {solutions_html}
  </section>"""


def _render_masthead(root_label: str) -> str:
    """The root entity's own name, prominent at the very top of the
    document -- so which requirement/solution tree a given report was
    generated from is never ambiguous, matching the page's own <title>
    (see _report_title)."""
    return f"""
  <div class="masthead">
    <p class="kicker">requirement tree</p>
    <h1>{html.escape(root_label)}</h1>
  </div>"""


def _render_toc_section(requirement_nodes: list[dict]) -> str:
    items_html = "".join(
        f'<li><a href="#{_requirement_anchor(n["key"])}">{html.escape(n["label"])}</a></li>'
        for n in requirement_nodes
    )
    return f"""
  <p class="toc-heading">Contents</p>
  <nav class="toc"><ul class="toc-root">{items_html}</ul></nav>"""


def _render_solutions_section(subtree: dict) -> str:
    # Exclude the root itself: it's the tree's own starting point (usually
    # a solution to something outside this subtree entirely), not a
    # candidate competing with the requirements' own solutions below it.
    solution_nodes = [
        n for n in subtree["nodes"] if n["type"] == "solution" and n["parent_id"] is not None
    ]
    solution_nodes.sort(key=lambda n: n["key"])
    selected_nodes = [n for n in solution_nodes if n["selected"]]
    unselected_nodes = [n for n in solution_nodes if not n["selected"]]
    selected_html = "".join(
        _render_solution(n, subtree, show_requirements=True) for n in selected_nodes
    ) or '<p class="no-solutions">None yet.</p>'
    unselected_html = "".join(
        _render_solution(n, subtree, show_requirements=True) for n in unselected_nodes
    ) or '<p class="no-solutions">None -- every candidate solution has been selected.</p>'
    return f"""
  <div class="masthead">
    <p class="kicker">solution index</p>
    <h1>Solutions</h1>
    <p class="subtitle">
      Every candidate solution once, regardless of how many requirements it
      covers. Expand a solution to see what it solves, its pros and cons.
    </p>
  </div>
  <h2 class="solutions-subheading">Selected</h2>
  {selected_html}
  <h2 class="solutions-subheading">Unselected</h2>
  {unselected_html}"""


def _render_dependency(key: str, dependencies_data: dict) -> str:
    entity = dependencies_data["entities"][key]
    description = html.escape(entity["description"])
    work_state = entity["work_state"]
    location = entity["location"]
    solution_labels = dependencies_data["dependency_to_solutions"].get(key, [])
    chips = "".join(
        f'<span class="req-chip">{html.escape(s.replace("_", " "))}</span>' for s in solution_labels
    ) or '<span class="req-chip req-chip-none">none currently</span>'
    return f"""
      <details class="solution">
        <summary>
          <span class="solution-name dependency-location">{html.escape(location)}</span>
          <span class="work-state work-state-{html.escape(work_state.replace(' ', '-'))}">{html.escape(work_state)}</span>
        </summary>
        <div class="solution-body">
          <p class="solution-description">{description}</p>
          <p class="section-label">Needed by</p>
          <div class="req-chips">{chips}</div>
        </div>
      </details>"""


def _render_dependencies_section(dependencies_data: dict) -> str:
    keys = sorted(dependencies_data["entities"])
    items_html = "".join(_render_dependency(k, dependencies_data) for k in keys)
    return f"""
  <div class="masthead">
    <p class="kicker">dependencies</p>
    <h1>Dependencies</h1>
    <p class="subtitle">
      Concrete entities the selected solutions above still need built,
      gathered here once each.
    </p>
  </div>
  {items_html}"""


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

  .toc-heading {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--muted-2); margin: 0 0 0.5rem;
  }
  nav.toc { margin-bottom: 2.75rem; }
  ul.toc-root { list-style: none; margin: 0; padding: 0; }
  ul.toc-root li { border-top: 1px solid var(--border); }
  ul.toc-root li:last-child { border-bottom: 1px solid var(--border); }
  ul.toc-root a {
    display: block; padding: 0.65rem 0.1rem;
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-weight: 600;
    font-size: 0.95rem; color: var(--fg); text-decoration: none;
  }
  ul.toc-root a:hover { color: var(--accent); }

  .requirement { margin-bottom: 2.75rem; scroll-margin-top: 1.5rem; }
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
  details.solution.solution-selected { border-color: var(--pro); background: var(--pro-bg); }
  details.solution.solution-selected summary::before { color: var(--pro); }
  .selected-badge {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.66rem; font-weight: 600; letter-spacing: 0.04em;
    padding: 0.12rem 0.5rem; border-radius: 5px;
    background: var(--pro); color: var(--accent-fg); white-space: nowrap;
  }
  .solutions-subheading {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.05rem; font-weight: 600; margin: 1.8rem 0 0;
  }
  .solution-name { flex: 1; font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.95rem; }
  .dependency-location { font-size: 0.85rem; overflow-wrap: anywhere; }
  .work-state {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-weight: 500; font-size: 0.68rem; letter-spacing: 0.03em;
    padding: 0.2rem 0.55rem; border-radius: 999px;
    background: var(--chip-bg); color: var(--chip-fg); white-space: nowrap;
  }
  .work-state-done { background: var(--pro-bg); color: var(--pro); }
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

  .section-label {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--muted-2); margin: 0.9rem 0 0.4rem;
  }
  .req-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .req-chip {
    font-size: 0.8rem; padding: 0.2rem 0.6rem; border-radius: 999px;
    background: var(--chip-bg); color: var(--chip-fg);
  }
  .req-chip-none { font-style: italic; }

  .code-example {
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 0.85rem 1rem; overflow-x: auto; margin: 0;
  }
  .code-example code {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.8rem; line-height: 1.5; color: var(--fg); white-space: pre;
  }

  .section-divider { border: none; border-top: 1px solid var(--border); margin: 3rem 0 2.75rem; }
"""

def _root_label(subtree: dict) -> str:
    root = next(n for n in subtree["nodes"] if n["parent_id"] is None)
    return root["label"]


def render_report(subtree: dict, dependencies_data: dict | None, fragment: bool) -> str:
    root_label = _root_label(subtree)
    requirement_nodes = sorted(
        (n for n in subtree["nodes"] if n["type"] == "requirement"),
        key=lambda n: n["key"],
    )
    masthead_html = _render_masthead(root_label)
    toc_html = _render_toc_section(requirement_nodes)
    requirements_html = "".join(_render_requirement(n, subtree) for n in requirement_nodes)
    solutions_html = _render_solutions_section(subtree)
    body_parts = [masthead_html, toc_html, requirements_html, '<hr class="section-divider">', solutions_html]
    if dependencies_data:
        body_parts.append('<hr class="section-divider">')
        body_parts.append(_render_dependencies_section(dependencies_data))
    body = "".join(body_parts)

    title = f"{root_label} · Requirement Tree"
    if fragment:
        return f'<title>{html.escape(title)}</title>\n<style>{_STYLE}</style>\n{body}\n'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Entity key to root the report at.")
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
    dependencies_data = load_dependencies_data(registrar, args.root)
    content = render_report(subtree, dependencies_data, args.fragment)
    args.output.write_text(content)
    requirement_count = sum(1 for n in subtree["nodes"] if n["type"] == "requirement")
    solution_count = sum(1 for n in subtree["nodes"] if n["type"] == "solution")
    print(f"Wrote {args.output} ({requirement_count} requirement(s), {solution_count} solution(s))")


if __name__ == "__main__":
    main()
