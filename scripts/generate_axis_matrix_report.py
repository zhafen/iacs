#!/usr/bin/env python3
"""Generate an HTML report of an axis/matrix subtree in an iacs manifest:
two or more independent choice axes (each holding an ordered set of level
entities), evaluated against a shared set of measures_of_success.

Unlike generate_requirement_tree_report.py, this doesn't walk
requirement/solution relations -- there's nothing to walk. An axis level
isn't a candidate solution competing for one slot; it's a point on a
dimension, rated independently against each measure via a plain
consideration_rating (value = the measure's own string key, not an
entity_ref, so no relation resolution is needed at all).

Structural discovery, no hardcoded entity names: within the subtree
rooted at --root,
  - "measures" are entities carrying a `consideration` component,
  - "axes" are the direct children of root whose own children are NOT
    measures (i.e. every child of root except the one measures container),
  - "levels" are the children of each axis.

Run: uv run python scripts/generate_axis_matrix_report.py --root <entity_key> [--manifest DIR ...] [--output PATH] [--fragment]
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from iacs.commands import parse_manifest_env
from iacs.registrar import Registrar

DEFAULT_OUTPUT = Path("/tmp/axis_matrix_report.html")


def _clean(path: str) -> str:
    return path.split(":", 1)[1]


def load_matrix(registrar, root_key: str) -> dict:
    entity_id = registrar.get("entity_id")
    eids = entity_id.execute()
    path_of = dict(zip(eids["value"].astype(str), eids["path"].astype(str)))

    def in_subtree(path: str) -> bool:
        return root_key in path.split(".")

    subtree_path_of = {eid: _clean(p) for eid, p in path_of.items() if in_subtree(_clean(p))}
    root_path = next(p for eid, p in subtree_path_of.items() if p.rsplit(".", 1)[-1] == root_key)
    root_depth = root_path.count(".")

    def depth_of(path: str) -> int:
        return path.count(".") - root_depth

    def parent_path(path: str) -> str:
        return path.rsplit(".", 1)[0]

    descriptions: dict[str, str] = {}
    for _, row in registrar.get("description").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            descriptions[eid] = str(row["value"])

    measures: dict[str, dict] = {}  # keyed by consideration's own string value (not eid)
    for _, row in registrar.get("consideration").execute().iterrows():
        eid = str(row["entity_id"])
        if eid in subtree_path_of:
            key = str(row["value"])
            measures[key] = {
                "eid": eid,
                "key": subtree_path_of[eid].rsplit(".", 1)[-1],
                "description": descriptions.get(eid, ""),
                "weight": float(row["weight"]) if row.get("weight") == row.get("weight") else 1.0,
            }

    measures_container_eid = None
    for eid, path in subtree_path_of.items():
        child_eids = [e for e, p in subtree_path_of.items() if parent_path(p) == path]
        if child_eids and all(
            any(m["eid"] == c for m in measures.values()) for c in child_eids
        ):
            measures_container_eid = eid
            break

    axis_eids = [
        eid
        for eid, path in subtree_path_of.items()
        if depth_of(path) == 1 and eid != measures_container_eid
    ]
    axes = []
    for axis_eid in sorted(axis_eids, key=lambda e: subtree_path_of[e]):
        axis_path = subtree_path_of[axis_eid]
        level_eids = [
            eid for eid, p in subtree_path_of.items() if parent_path(p) == axis_path
        ]
        levels = []
        for level_eid in sorted(level_eids, key=lambda e: subtree_path_of[e].rsplit(".", 1)[-1]):
            levels.append({
                "eid": level_eid,
                "key": subtree_path_of[level_eid].rsplit(".", 1)[-1],
                "description": descriptions.get(level_eid, ""),
            })
        axes.append({
            "eid": axis_eid,
            "key": subtree_path_of[axis_eid].rsplit(".", 1)[-1],
            "description": descriptions.get(axis_eid, ""),
            "levels": levels,
        })

    ratings: dict[str, list[dict]] = {}
    for _, row in registrar.get("consideration_rating").execute().iterrows():
        eid = str(row["entity_id"])
        if eid not in subtree_path_of:
            continue
        value = row.get("value")
        measure_key = None if (value is None or value != value) else str(value)
        ratings.setdefault(eid, []).append({
            "measure_key": measure_key,
            "rating": float(row["rating"]),
            "note": str(row["note"]),
        })

    return {"axes": axes, "measures": measures, "ratings": ratings, "root_label": root_key.replace("_", " ")}


def _rating_class(rating: float) -> str:
    return "rating-pro" if rating >= 0 else "rating-con"


def _render_rating(item: dict, measures: dict) -> str:
    measure_label = (
        measures[item["measure_key"]]["key"].replace("_", " ")
        if item["measure_key"] and item["measure_key"] in measures
        else "general"
    )
    sign = "+" if item["rating"] >= 0 else ""
    return f"""
        <li class="rating {_rating_class(item['rating'])}">
          <span class="rating-tag">{html.escape(measure_label)}</span>
          <span class="rating-score">{sign}{item['rating']:.1f}</span>
          <p class="rating-note">{html.escape(item['note'])}</p>
        </li>"""


def _render_level(level: dict, matrix: dict) -> str:
    items = matrix["ratings"].get(level["eid"], [])
    ratings_html = "".join(_render_rating(r, matrix["measures"]) for r in items) or (
        '<li class="rating rating-none">No ratings recorded yet.</li>'
    )
    return f"""
      <details class="level">
        <summary><span class="level-name">{html.escape(level['key'].replace('_', ' '))}</span></summary>
        <div class="level-body">
          <p class="level-description">{html.escape(level['description'])}</p>
          <ul class="ratings">{ratings_html}</ul>
        </div>
      </details>"""


def _render_axis(axis: dict, matrix: dict) -> str:
    levels_html = "".join(_render_level(lvl, matrix) for lvl in axis["levels"])
    return f"""
  <section class="axis">
    <p class="eyebrow">Axis</p>
    <h2>{html.escape(axis['key'].replace('_', ' '))}</h2>
    <p class="axis-description">{html.escape(axis['description'])}</p>
    {levels_html}
  </section>"""


def _render_measures_section(measures: dict) -> str:
    chips = "".join(
        f'<li class="measure-chip"><span class="measure-name">{html.escape(m["key"].replace("_", " "))}</span>'
        f'<span class="measure-weight">weight {m["weight"]:g}</span>'
        f'<p class="measure-description">{html.escape(m["description"])}</p></li>'
        for m in sorted(measures.values(), key=lambda m: m["key"])
    )
    return f"""
  <div class="masthead">
    <p class="kicker">measures of success</p>
    <h1>What every level gets rated against</h1>
  </div>
  <ul class="measures">{chips}</ul>"""


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
  .masthead { margin-bottom: 1.75rem; }
  .kicker {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 0.6rem;
  }
  h1 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.7rem; font-weight: 600; margin: 0 0 0.6rem;
  }
  .subtitle { color: var(--muted); margin: 0 0 2.75rem; font-size: 0.95rem; max-width: 62ch; }

  ul.measures { list-style: none; margin: 0 0 3rem; padding: 0; display: grid; gap: 0.6rem; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
  li.measure-chip {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 0.85rem 1rem;
  }
  .measure-name {
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-weight: 600; font-size: 0.88rem;
  }
  .measure-weight {
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.7rem; color: var(--muted);
    margin-left: 0.5rem; font-variant-numeric: tabular-nums;
  }
  .measure-description { margin: 0.4rem 0 0; color: var(--muted); font-size: 0.85rem; }

  .axis { margin-bottom: 2.75rem; }
  .eyebrow {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--accent); margin: 0 0 0.3rem;
  }
  .axis h2 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.25rem; font-weight: 600; margin: 0 0 0.5rem;
  }
  .axis-description { color: var(--muted); margin: 0 0 0.9rem; max-width: 62ch; }

  details.level {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    margin: 0.7rem 0; padding: 0 1.1rem;
  }
  details.level summary {
    cursor: pointer; padding: 0.85rem 0; list-style: none; font-weight: 600;
  }
  details.level summary::-webkit-details-marker { display: none; }
  details.level summary::before {
    content: "▸"; color: var(--muted-2); font-weight: normal; margin-right: 0.6rem;
    display: inline-block; transition: transform 0.15s ease;
  }
  details.level[open] summary::before { transform: rotate(90deg); }
  .level-name { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.95rem; }
  .level-body { padding: 0 0 1.1rem 1.5rem; }
  .level-description { color: var(--fg); margin-top: 0; max-width: 62ch; }

  ul.ratings { list-style: none; margin: 0.6rem 0 0; padding: 0; }
  li.rating {
    padding: 0.55rem 0; border-top: 1px solid var(--border);
    display: grid; grid-template-columns: auto auto 1fr; gap: 0.6rem; align-items: baseline;
  }
  li.rating:first-child { border-top: none; }
  .rating-tag {
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.68rem; font-weight: 600;
    letter-spacing: 0.03em; text-transform: uppercase; padding: 0.12rem 0.5rem;
    border-radius: 999px; background: var(--chip-bg); color: var(--chip-fg); white-space: nowrap;
  }
  .rating-score {
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.8rem; font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  li.rating.rating-pro .rating-score { color: var(--pro); }
  li.rating.rating-con .rating-score { color: var(--con); }
  .rating-note { grid-column: 1 / -1; margin: 0.2rem 0 0; color: var(--muted); font-size: 0.9rem; max-width: 62ch; }
  li.rating-none { color: var(--muted-2); font-style: italic; grid-template-columns: 1fr; }
"""


def render_report(matrix: dict, fragment: bool) -> str:
    masthead_html = f"""
  <div class="masthead">
    <p class="kicker">axis matrix</p>
    <h1>{html.escape(matrix['root_label'])}</h1>
  </div>"""
    measures_html = _render_measures_section(matrix["measures"])
    axes_html = "".join(_render_axis(a, matrix) for a in matrix["axes"])
    body = masthead_html + measures_html + axes_html

    title = f"{matrix['root_label']} · Axis Matrix"
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
    registrar = Registrar.from_manifest(manifest_paths)
    matrix = load_matrix(registrar, args.root)
    content = render_report(matrix, args.fragment)
    args.output.write_text(content)
    print(
        f"Wrote {args.output} ({len(matrix['axes'])} axis/axes, "
        f"{sum(len(a['levels']) for a in matrix['axes'])} level(s), "
        f"{len(matrix['measures'])} measure(s))"
    )


if __name__ == "__main__":
    main()
