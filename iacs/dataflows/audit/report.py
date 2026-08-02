"""Hamilton DAG that renders a polished, self-contained HTML audit report.

Combines an aggregated cost-impact scatter plot (see
``iacs.dataflows.derive.impact_cost``) with a navigable requirements tree
(see ``iacs.views.requirement_tree``) into a single HTML file that can be
opened directly in a browser.
"""

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir

from ...registry import Registry
from ...views.requirement_tree import build_requirement_forest


INPUT_COMPONENT_TYPES = ["entity_id", "resolved_impact_cost"]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow."""
    return {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES}


def requirement_tree_data(registry: Registry) -> dict:
    """Build the navigable requirement tree as a D3-hierarchy-ready dict."""
    return build_requirement_forest(registry)


def cost_impact_data(resolved_impact_cost: ir.Table, entity_id: ir.Table) -> list[dict]:
    """Build one row per entity (label, impact, cost, diff, ratio) for the scatter plot.

    Parameters
    ----------
    resolved_impact_cost : ir.Table
        Normalized per-entity impact/cost totals, as produced by
        ``derive.impact_cost``.
    entity_id : ir.Table
        The entity spine table, used to resolve human-readable labels.

    Returns
    -------
    list[dict]
        Rows sorted by label, each with keys: label, impact, cost, diff, ratio.
    """
    df = resolved_impact_cost.to_pandas()
    if df.empty:
        return []
    id_to_key = entity_id.to_pandas().set_index("value")["entity_key"].to_dict()
    df = df.copy()
    df["label"] = df["entity_id"].map(id_to_key).fillna(df["entity_id"].str.slice(0, 8))
    df = df.sort_values("label")
    return df[["label", "impact", "cost", "diff", "ratio"]].round(4).to_dict(orient="records")


def _safe_json_dumps(data) -> str:
    """Serialize to JSON for embedding directly as JS source inside a <script> tag.

    Escapes '<', '>', and '&' so a label containing e.g. "</script>" can't
    prematurely close the surrounding script tag (the classic JSON-in-HTML
    injection); the escapes are valid inside a JS/JSON string literal, so
    the embedded values are unaffected once parsed.
    """
    return (
        json.dumps(data)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _json_safe(data: list[dict]) -> list[dict]:
    """Replace non-finite floats (inf/-inf/nan) with None so the value serializes as JS null."""
    def clean(v):
        return None if isinstance(v, float) and not math.isfinite(v) else v
    return [{k: clean(v) for k, v in row.items()} for row in data]


def _cost_impact_table_rows(data: list[dict]) -> str:
    """Render a static (JS-independent) fallback table for the cost-impact data."""
    if not data:
        return '<tr><td colspan="5" class="empty">No impact/cost data available.</td></tr>'
    rows = []
    for row in data:
        ratio = row["ratio"]
        ratio_str = f"{ratio:.2f}" if math.isfinite(ratio) else "∞"
        rows.append(
            "<tr><td>{label}</td><td>{impact:.2f}</td><td>{cost:.2f}</td>"
            "<td>{diff:+.2f}</td><td>{ratio}</td></tr>".format(
                label=html.escape(str(row["label"])),
                impact=row["impact"],
                cost=row["cost"],
                diff=row["diff"],
                ratio=ratio_str,
            )
        )
    return "\n".join(rows)


def report_html(requirement_tree_data: dict, cost_impact_data: list[dict]) -> str:
    """Render the full self-contained HTML report.

    Parameters
    ----------
    requirement_tree_data : dict
        Nested {name, priority, children} dict, as returned by
        ``build_requirement_forest``.
    cost_impact_data : list[dict]
        Per-entity impact/cost rows, as returned by ``cost_impact_data``.

    Returns
    -------
    str
        The rendered HTML document.
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = _TEMPLATE
    out = out.replace("@GENERATED_AT@", html.escape(generated_at))
    out = out.replace("@COST_IMPACT_JSON@", _safe_json_dumps(_json_safe(cost_impact_data)))
    out = out.replace("@REQUIREMENT_TREE_JSON@", _safe_json_dumps(requirement_tree_data))
    out = out.replace("@COST_IMPACT_TABLE_ROWS@", _cost_impact_table_rows(cost_impact_data))
    return out


def report_path(report_html: str, output_path: str = "iacs_report.html") -> str:
    """Write the rendered report to disk.

    Parameters
    ----------
    report_html : str
        The rendered HTML document.
    output_path : str
        File path to write the report to. Defaults to "iacs_report.html" in
        the current directory.

    Returns
    -------
    str
        The path the report was written to.
    """
    path = Path(output_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_html, encoding="utf-8")
    return str(path)


FINAL_VAR = "report_path"


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iacs Audit Report</title>
<style>
  :root {
    color-scheme: light;
    --page:        #f9f9f7;
    --surface:     #fcfcfb;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:    #e1e0d9;
    --baseline:    #c3c2b7;
    --border:      rgba(11,11,11,0.10);
    --pos:         #2a78d6;
    --neg:         #e34948;
    --neutral:     #f0efec;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --page:        #0d0d0d;
      --surface:     #1a1a19;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --gridline:    #2c2c2a;
      --baseline:    #383835;
      --border:      rgba(255,255,255,0.10);
      --pos:         #3987e5;
      --neg:         #e66767;
      --neutral:     #383835;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --page:        #0d0d0d;
    --surface:     #1a1a19;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --gridline:    #2c2c2a;
    --baseline:    #383835;
    --border:      rgba(255,255,255,0.10);
    --pos:         #3987e5;
    --neg:         #e66767;
    --neutral:     #383835;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--page);
    color: var(--text-primary);
  }
  main {
    max-width: 1080px;
    margin: 0 auto;
    padding: 32px 20px 64px;
  }
  header h1 {
    font-size: 22px;
    margin: 0 0 4px;
  }
  header p {
    margin: 0 0 32px;
    color: var(--text-secondary);
    font-size: 13px;
  }
  section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 24px;
    overflow-x: auto;
  }
  section h2 {
    font-size: 16px;
    margin: 0 0 4px;
  }
  section > p.lede {
    margin: 0 0 16px;
    color: var(--text-secondary);
    font-size: 13px;
  }
  .empty {
    color: var(--text-muted);
    font-style: italic;
  }

  /* -- cost/impact scatter -- */
  #cost-impact-chart {
    width: 100%;
    height: auto;
    overflow: visible;
  }
  .axis text {
    fill: var(--text-muted);
    font-size: 11px;
  }
  .axis path, .axis line {
    stroke: var(--gridline);
    shape-rendering: crispEdges;
  }
  .gridline {
    stroke: var(--gridline);
  }
  .breakeven {
    stroke: var(--baseline);
    stroke-width: 1;
    stroke-dasharray: 4 3;
    fill: none;
  }
  .axis-label {
    fill: var(--text-secondary);
    font-size: 12px;
  }
  .dot {
    stroke: var(--surface);
    stroke-width: 2px;
  }
  .hit {
    fill: transparent;
    cursor: pointer;
  }
  .legend-gradient-label {
    fill: var(--text-secondary);
    font-size: 11px;
  }
  #tooltip {
    position: fixed;
    pointer-events: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    opacity: 0;
    transition: opacity 0.1s;
    z-index: 10;
    max-width: 220px;
  }
  #tooltip .tt-title {
    color: var(--text-secondary);
    margin-bottom: 4px;
  }
  #tooltip .tt-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }
  #tooltip .tt-row span:first-child {
    color: var(--text-secondary);
  }
  #tooltip .tt-row span:last-child {
    color: var(--text-primary);
    font-weight: 600;
  }

  details.table-toggle summary {
    cursor: pointer;
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 12px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin-top: 10px;
    font-size: 12px;
  }
  table th, table td {
    text-align: right;
    padding: 4px 10px;
    border-bottom: 1px solid var(--gridline);
    font-variant-numeric: tabular-nums;
  }
  table th:first-child, table td:first-child {
    text-align: left;
    font-variant-numeric: normal;
  }
  table th {
    color: var(--text-muted);
    font-weight: 500;
  }

  /* -- requirement tree -- */
  #tree-wrap {
    border: 1px solid var(--border);
    border-radius: 8px;
    height: 520px;
    overflow: hidden;
    cursor: grab;
    background: var(--surface);
  }
  #tree-wrap:active { cursor: grabbing; }
  #tree-canvas { width: 100%; height: 100%; display: block; }
  .req-node circle {
    stroke-width: 2px;
    fill: var(--surface);
    stroke: var(--pos);
    transition: fill 0.15s;
  }
  .req-node text {
    font-size: 12px;
    fill: var(--text-primary);
    pointer-events: none;
  }
  .req-node .priority {
    fill: var(--text-muted);
    font-size: 10px;
  }
  .req-link {
    fill: none;
    stroke: var(--baseline);
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>iacs Audit Report</h1>
    <p>Generated @GENERATED_AT@</p>
  </header>

  <section id="cost-impact-section">
    <h2>Aggregated Cost vs. Impact</h2>
    <p class="lede">Each point is one entity's total normalized impact and cost. Points above the dashed line return more impact than they cost; color shows the size of that gap.</p>
    <svg id="cost-impact-chart"></svg>
    <details class="table-toggle">
      <summary>Show as table</summary>
      <table>
        <thead>
          <tr><th>Entity</th><th>Impact</th><th>Cost</th><th>Diff</th><th>Ratio</th></tr>
        </thead>
        <tbody>
          @COST_IMPACT_TABLE_ROWS@
        </tbody>
      </table>
    </details>
  </section>

  <section id="requirement-tree-section">
    <h2>Requirements</h2>
    <p class="lede">Click a node to expand or collapse it, scroll to zoom, drag to pan.</p>
    <div id="tree-wrap"><svg id="tree-canvas"></svg></div>
  </section>
</main>

<div id="tooltip"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const costImpactData = @COST_IMPACT_JSON@;
const requirementTreeData = @REQUIREMENT_TREE_JSON@;

// ---------------------------------------------------------------------
// Cost / impact scatter
// ---------------------------------------------------------------------
(function renderCostImpactChart() {
  const container = document.getElementById("cost-impact-section");
  const svg = d3.select("#cost-impact-chart");
  const tooltip = document.getElementById("tooltip");

  if (!costImpactData.length) {
    svg.remove();
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "No impact/cost data available.";
    container.insertBefore(p, container.querySelector("details"));
    return;
  }

  const margin = { top: 40, right: 24, bottom: 44, left: 52 };
  const width = Math.max(container.clientWidth - 48, 320);
  const height = 420;
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  svg.attr("viewBox", `0 0 ${width} ${height}`);
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const maxVal = d3.max(costImpactData, d => Math.max(d.impact, d.cost)) || 1;
  const x = d3.scaleLinear().domain([0, maxVal * 1.08]).range([0, innerW]);
  const y = d3.scaleLinear().domain([0, maxVal * 1.08]).range([innerH, 0]);

  const diffs = costImpactData.map(d => d.diff);
  const diffExtent = Math.max(Math.abs(d3.min(diffs)), Math.abs(d3.max(diffs))) || 1;
  const color = d3.scaleDiverging()
    .domain([-diffExtent, 0, diffExtent])
    .interpolator(d3.interpolateRgbBasis([
      getComputedStyle(document.documentElement).getPropertyValue("--neg").trim(),
      getComputedStyle(document.documentElement).getPropertyValue("--neutral").trim(),
      getComputedStyle(document.documentElement).getPropertyValue("--pos").trim(),
    ]));

  // Gridlines
  g.append("g")
    .attr("class", "gridline")
    .selectAll("line")
    .data(y.ticks(6))
    .join("line")
    .attr("x1", 0).attr("x2", innerW)
    .attr("y1", d => y(d)).attr("y2", d => y(d));

  // Break-even reference line (impact == cost)
  g.append("line")
    .attr("class", "breakeven")
    .attr("x1", x(0)).attr("y1", y(0))
    .attr("x2", x(maxVal * 1.08)).attr("y2", y(maxVal * 1.08));

  // Axes
  g.append("g")
    .attr("class", "axis")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(x).ticks(6));
  g.append("g")
    .attr("class", "axis")
    .call(d3.axisLeft(y).ticks(6));

  g.append("text")
    .attr("class", "axis-label")
    .attr("x", innerW / 2).attr("y", innerH + 36)
    .attr("text-anchor", "middle")
    .text("Cost");
  g.append("text")
    .attr("class", "axis-label")
    .attr("transform", "rotate(-90)")
    .attr("x", -innerH / 2).attr("y", -38)
    .attr("text-anchor", "middle")
    .text("Impact");

  // Points: visible dot + larger transparent hit target (>=24px)
  const points = g.selectAll("g.point")
    .data(costImpactData)
    .join("g")
    .attr("class", "point")
    .attr("transform", d => `translate(${x(d.cost)},${y(d.impact)})`);

  points.append("circle")
    .attr("class", "dot")
    .attr("r", 6)
    .attr("fill", d => color(d.diff));

  points.append("circle")
    .attr("class", "hit")
    .attr("r", 12)
    .on("pointerenter pointermove", (event, d) => {
      const ratioText = Number.isFinite(d.ratio) ? d.ratio.toFixed(2) : "—";
      tooltip.innerHTML = "";
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = d.label;
      tooltip.appendChild(title);
      [
        ["Impact", d.impact.toFixed(2)],
        ["Cost", d.cost.toFixed(2)],
        ["Diff", (d.diff >= 0 ? "+" : "") + d.diff.toFixed(2)],
        ["Ratio", ratioText],
      ].forEach(([k, v]) => {
        const row = document.createElement("div");
        row.className = "tt-row";
        const kEl = document.createElement("span");
        kEl.textContent = k;
        const vEl = document.createElement("span");
        vEl.textContent = v;
        row.appendChild(kEl);
        row.appendChild(vEl);
        tooltip.appendChild(row);
      });
      tooltip.style.opacity = 1;
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top = (event.clientY + 14) + "px";
    })
    .on("pointerleave", () => { tooltip.style.opacity = 0; });

  // Diverging color legend
  const legendW = 220, legendH = 10;
  const legendG = svg.append("g")
    .attr("transform", `translate(${margin.left},${8})`);
  const gradId = "diff-gradient";
  const defs = svg.append("defs");
  const grad = defs.append("linearGradient").attr("id", gradId);
  grad.selectAll("stop")
    .data([0, 0.5, 1])
    .join("stop")
    .attr("offset", d => d * 100 + "%")
    .attr("stop-color", d => color(-diffExtent + d * 2 * diffExtent));
  legendG.append("rect")
    .attr("width", legendW).attr("height", legendH)
    .attr("fill", `url(#${gradId})`)
    .attr("rx", 3);
  legendG.append("text")
    .attr("class", "legend-gradient-label")
    .attr("x", 0).attr("y", legendH + 14)
    .text("More cost");
  legendG.append("text")
    .attr("class", "legend-gradient-label")
    .attr("x", legendW).attr("y", legendH + 14)
    .attr("text-anchor", "end")
    .text("More impact");
})();

// ---------------------------------------------------------------------
// Navigable requirement tree
// ---------------------------------------------------------------------
(function renderRequirementTree() {
  const wrap = document.getElementById("tree-wrap");
  const svg = d3.select("#tree-canvas");
  const g = svg.append("g");

  let NODE_W = 210;
  const NODE_H = 26;

  const zoom = d3.zoom()
    .scaleExtent([0.1, 3])
    .on("zoom", e => g.attr("transform", e.transform));
  svg.call(zoom);

  let nodeId = 0;
  const _ctx = document.createElement("canvas").getContext("2d");
  _ctx.font = "12px sans-serif";
  function textWidth(str) { return _ctx.measureText(str).width; }

  if (!requirementTreeData || (!requirementTreeData.children && requirementTreeData.name === undefined)) {
    wrap.innerHTML = '<p class="empty" style="padding:16px;">No requirements found.</p>';
    return;
  }

  const root = d3.hierarchy(requirementTreeData);
  root.x0 = 0;
  root.y0 = 0;

  let maxW = 0;
  root.each(d => {
    const label = d.data.name + (d.data.priority != null ? ` (${d.data.priority.toFixed(2)})` : "");
    maxW = Math.max(maxW, textWidth(label));
  });
  NODE_W = maxW + 40;

  root.children && root.children.forEach(collapse);
  update(root);

  const { height } = svg.node().getBoundingClientRect();
  svg.call(zoom.transform, d3.zoomIdentity.translate(80, height / 2));

  function collapse(d) {
    if (d.children) {
      d._children = d.children;
      d._children.forEach(collapse);
      d.children = null;
    }
  }

  function rootRef(node) {
    let n = node;
    while (n.parent) n = n.parent;
    return n;
  }

  function update(source) {
    const treeFn = d3.tree().nodeSize([NODE_H, NODE_W]);
    treeFn(rootRef(source));

    const nodes = rootRef(source).descendants();
    const links = rootRef(source).links();

    const node = g.selectAll("g.req-node").data(nodes, d => d.uid || (d.uid = ++nodeId));

    const enter = node.enter().append("g")
      .attr("class", "req-node")
      .attr("transform", `translate(${source.y0},${source.x0})`)
      .style("cursor", "pointer")
      .on("click", (_, d) => {
        if (d.children) { d._children = d.children; d.children = null; }
        else { d.children = d._children; d._children = null; }
        update(d);
      });

    enter.append("circle").attr("r", 0);

    const textEl = enter.append("text")
      .attr("dy", "0.35em")
      .attr("x", d => d.children || d._children ? -10 : 10)
      .attr("text-anchor", d => d.children || d._children ? "end" : "start");
    textEl.append("tspan").text(d => d.data.name);
    textEl.append("tspan")
      .attr("class", "priority")
      .text(d => d.data.priority != null ? ` (${d.data.priority.toFixed(2)})` : "");

    const merged = enter.merge(node);

    merged.transition().duration(220)
      .attr("transform", d => `translate(${d.y},${d.x})`);

    merged.select("circle").transition().duration(220)
      .attr("r", 5)
      .style("fill", d => d._children ? "var(--pos)" : "var(--surface)");

    merged.select("text")
      .attr("x", d => d.children || d._children ? -10 : 10)
      .attr("text-anchor", d => d.children || d._children ? "end" : "start");

    node.exit().transition().duration(220)
      .attr("transform", `translate(${source.y},${source.x})`)
      .remove()
      .select("circle").attr("r", 0);

    const link = g.selectAll("path.req-link").data(links, d => d.target.uid);

    const diagonal = d3.linkHorizontal().x(d => d.y).y(d => d.x);
    const collapsed = { x: source.x0, y: source.y0 };

    link.enter().insert("path", "g")
      .attr("class", "req-link")
      .style("stroke-width", d => `${Math.max(0.5, (d.target.data.priority || 0.5) * 4)}px`)
      .attr("d", () => diagonal({ source: collapsed, target: collapsed }))
      .merge(link).transition().duration(220)
      .style("stroke-width", d => `${Math.max(0.5, (d.target.data.priority || 0.5) * 4)}px`)
      .attr("d", diagonal);

    link.exit().transition().duration(220)
      .attr("d", () => diagonal({ source: { x: source.x, y: source.y }, target: { x: source.x, y: source.y } }))
      .remove();

    nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
  }
})();
</script>
</body>
</html>
"""
