# Visualizations

## Effort vs. Priority

This chart shows each entity's **effort sum** (total story points) versus its **priority product** (the product of requirement priorities along its hierarchy). High-priority, high-effort items may warrant breaking down or deferring; high-priority, low-effort items are quick wins.

<div id="scatter-container">
<svg id="scatter"></svg>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function () {
  const data = [
  {"name":"two_pass_llm","entity_alias":"overall_approach.two_pass_llm","effort_sum":8.0,"priority_product":0.5},
  {"name":"transform_functionality","entity_alias":"ecs_system.transform_functionality","effort_sum":13.0,"priority_product":0.5},
  {"name":"connectivity_audit","entity_alias":"builtin_audits.connectivity_audit","effort_sum":5.0,"priority_product":0.5},
  {"name":"parse_natural_language","entity_alias":"parse_infrastructure_in_a_wide_variety_of_formats.parse_natural_language","effort_sum":21.0,"priority_product":0.5},
  {"name":"parse_a_variety_of_IaC_formats","entity_alias":"parse_infrastructure_in_a_wide_variety_of_formats.parse_a_variety_of_IaC_formats","effort_sum":13.0,"priority_product":0.5},
  {"name":"registry","entity_alias":"ecs_system.registry","effort_sum":5.0,"priority_product":0.5},
  {"name":"parse_code_languages","entity_alias":"parse_infrastructure_in_a_wide_variety_of_formats.parse_code_languages","effort_sum":8.0,"priority_product":0.5},
  {"name":"requirement_coverage_audit","entity_alias":"builtin_audits.requirement_coverage_audit","effort_sum":3.0,"priority_product":0.5},
  {"name":"facilitate_compatibility_with_agents","entity_alias":"provide_a_launching_point_for_infrastructure_implementation.facilitate_compatibility_with_agents","effort_sum":8.0,"priority_product":0.5},
  {"name":"export_infrastructure_to_wiki","entity_alias":"have_good_formats.export_infrastructure_to_wiki","effort_sum":5.0,"priority_product":0.5},
  {"name":"todo_audit","entity_alias":"builtin_audits.todo_audit","effort_sum":2.0,"priority_product":0.5},
  {"name":"prioritization_audit","entity_alias":"builtin_audits.prioritization_audit","effort_sum":8.0,"priority_product":0.5},
  {"name":"traceability_audit","entity_alias":"builtin_audits.traceability_audit","effort_sum":3.0,"priority_product":0.5},
  {"name":"provide_functionality_for_prioritizing","entity_alias":"provide_a_guided_process_for_developing_solutions.provide_functionality_for_prioritizing","effort_sum":8.0,"priority_product":1.0},
  {"name":"agentic_registry_approach","entity_alias":"overall_approach.agentic_registry_approach","effort_sum":13.0,"priority_product":0.5},
  {"name":"definition_audit","entity_alias":"builtin_audits.definition_audit","effort_sum":5.0,"priority_product":0.5},
  {"name":"transform_between_entity_first_and_component_first","entity_alias":"transform_between_formats.transform_between_entity_first_and_component_first","effort_sum":8.0,"priority_product":0.9},
  {"name":"single_pass_llm","entity_alias":"overall_approach.single_pass_llm","effort_sum":5.0,"priority_product":0.5},
  {"name":"io_system","entity_alias":"ecs_system.io_system","effort_sum":8.0,"priority_product":0.5},
  {"name":"facilitate_compatibility_with_relational_databases","entity_alias":"provide_a_launching_point_for_infrastructure_implementation.facilitate_compatibility_with_relational_databases","effort_sum":8.0,"priority_product":0.5},
  {"name":"facilitate_compatibility_with_terraform","entity_alias":"provide_a_launching_point_for_infrastructure_implementation.facilitate_compatibility_with_terraform","effort_sum":13.0,"priority_product":0.5}
];

  const margin = { top: 40, right: 40, bottom: 70, left: 70 };
  const width = 700 - margin.left - margin.right;
  const height = 450 - margin.top - margin.bottom;

  const svg = d3.select("#scatter")
    .attr("width", width + margin.left + margin.right)
    .attr("height", height + margin.top + margin.bottom)
    .style("font-family", "inherit")
    .append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear()
    .domain([0, 1.05])
    .range([0, width]);

  const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => d.effort_sum) * 1.1])
    .range([height, 0]);

  // Gridlines
  svg.append("g")
    .attr("class", "grid")
    .attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).tickSize(-height).tickFormat(""))
    .selectAll("line").style("stroke", "#e0e0e0").style("stroke-dasharray", "3,3");

  svg.append("g")
    .attr("class", "grid")
    .call(d3.axisLeft(y).tickSize(-width).tickFormat(""))
    .selectAll("line").style("stroke", "#e0e0e0").style("stroke-dasharray", "3,3");

  // Axes
  svg.append("g")
    .attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).ticks(5));

  svg.append("g")
    .call(d3.axisLeft(y).ticks(6));

  // Axis labels
  svg.append("text")
    .attr("text-anchor", "middle")
    .attr("x", width / 2)
    .attr("y", height + 50)
    .style("font-size", "13px")
    .text("Priority Product");

  svg.append("text")
    .attr("text-anchor", "middle")
    .attr("transform", "rotate(-90)")
    .attr("x", -height / 2)
    .attr("y", -52)
    .style("font-size", "13px")
    .text("Effort Sum (story points)");

  // Tooltip
  const tooltip = d3.select("#scatter-container")
    .append("div")
    .style("position", "absolute")
    .style("background", "rgba(0,0,0,0.75)")
    .style("color", "#fff")
    .style("padding", "8px 12px")
    .style("border-radius", "4px")
    .style("font-size", "12px")
    .style("pointer-events", "none")
    .style("opacity", 0)
    .style("max-width", "260px")
    .style("line-height", "1.5");

  // Color scale by parent group
  const parents = [...new Set(data.map(d => d.entity_alias.split(".")[0]))];
  const color = d3.scaleOrdinal(d3.schemeTableau10).domain(parents);

  // Dots
  svg.selectAll("circle")
    .data(data)
    .join("circle")
    .attr("cx", d => x(d.priority_product))
    .attr("cy", d => y(d.effort_sum))
    .attr("r", 7)
    .attr("fill", d => color(d.entity_alias.split(".")[0]))
    .attr("opacity", 0.8)
    .attr("stroke", "#fff")
    .attr("stroke-width", 1.5)
    .on("mouseover", function (event, d) {
      d3.select(this).attr("r", 10).attr("opacity", 1);
      tooltip.transition().duration(100).style("opacity", 1);
      tooltip.html(
        `<strong>${d.name.replace(/_/g, " ")}</strong><br/>` +
        `<em>${d.entity_alias.split(".")[0].replace(/_/g, " ")}</em><br/>` +
        `Effort: ${d.effort_sum} pts<br/>` +
        `Priority product: ${d.priority_product}`
      )
        .style("left", (event.offsetX + 15) + "px")
        .style("top", (event.offsetY - 10) + "px");
    })
    .on("mousemove", function (event) {
      tooltip
        .style("left", (event.offsetX + 15) + "px")
        .style("top", (event.offsetY - 10) + "px");
    })
    .on("mouseout", function () {
      d3.select(this).attr("r", 7).attr("opacity", 0.8);
      tooltip.transition().duration(200).style("opacity", 0);
    });

  // Legend
  const legend = svg.append("g").attr("transform", `translate(${width - 10}, 0)`);
  parents.forEach((p, i) => {
    const g = legend.append("g").attr("transform", `translate(0, ${i * 18})`);
    g.append("circle").attr("r", 5).attr("fill", color(p));
    g.append("text")
      .attr("x", 9)
      .attr("dy", "0.35em")
      .style("font-size", "10px")
      .text(p.replace(/_/g, " ").replace(/provide a launching point for infrastructure implementation/, "launch point..."));
  });
})();
</script>

<style>
#scatter-container { position: relative; overflow: visible; }
#scatter .grid .domain { display: none; }
</style>
