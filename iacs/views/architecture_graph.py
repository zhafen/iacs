"""View helpers for building architecture graphs from parsed Python source.

Two complementary views over the same ``calls``/``imports`` entity_ref
relations that ``emc2p.dataflows.etl.load_python`` extracts (module/class/
function calls and imports, resolved to target entities where the target
is itself a qualifying entity -- see that module's ``_make_components``):

- ``build_architecture_graph``: every file in the loaded manifest,
  collapsed to one node per file -- the whole-project overview.
- ``build_call_reachability``: one specific entity (an "entry point"), and
  everything reachable from it by following ``calls`` edges outward,
  entity by entity -- the zoomed-in trace, not collapsed, and keeping
  same-file edges the overview graph drops as uninformative at that
  granularity.
"""

from pathlib import Path

from iacs.registrar import Registrar
from emc2p.utils import candidate_entity_ids


def _module_label(filepath: str) -> str:
    """Short readable label for a source filepath, e.g. 'iacs/registrar.py' -> 'registrar'."""
    stem = filepath.rsplit("/", 1)[-1]
    return stem[:-3] if stem.endswith(".py") else stem


def _file_node_label(filepath: str) -> str:
    """Full-path label for a per-file node, e.g. 'iacs/registrar.py' ->
    'iacs/registrar' -- unlike ``_module_label``'s bare stem (used for a
    reachability trace's own per-file *subgraph titles*, where the
    grouping itself already disambiguates), a whole-project overview's
    nodes carry no such grouping, so two same-named files from different
    directories (or different ``--manifest`` roots entirely) would
    otherwise render as identical, indistinguishable labels."""
    return filepath[:-3] if filepath.endswith(".py") else filepath


def build_architecture_graph(registrar: Registrar) -> dict:
    """Aggregate parsed-Python entities into a per-file call/import graph.

    Every entity ``load_python`` extracts carries the ``filepath`` of the
    source file it was defined in (on the ``entity_id`` component); this
    collapses entity-level ``calls``/``imports`` edges up to that file,
    the same collapsing ``iacs/docs/gen_dag_images.py`` does for Hamilton
    subdags, applied to application code instead. An edge only exists once
    its target has resolved to a known entity_id (``value_eid`` not null)
    -- calls to undocumented functions or third-party/stdlib code are
    dropped, same as they'd be silently unresolved anywhere else in iacs.
    Self-edges (a file calling/importing something in itself) are dropped
    too, since they add no information to a *file-structure* diagram.

    Args:
        registrar: A Registrar (or Registry) with loaded registry data,
            typically from parsing a package's Python source via
            ``load_manifest``.

    Returns:
        ``{"nodes": [{"id": filepath, "label": str}, ...], "edges":
        [{"source": filepath, "target": filepath, "kind": "calls" |
        "imports"}, ...]}``, both lists sorted for stable output.
    """
    entity_id_df = registrar.get("entity_id").to_pandas()
    if "filepath" in entity_id_df.columns:
        id_to_filepath = entity_id_df.set_index("value")["filepath"].to_dict()
    else:
        id_to_filepath = {}

    # calls/imports only ever come from parsed .py files (see load_python.py)
    # -- a YAML-sourced entity (a requirement, a component-type definition)
    # would only ever show up as an edgeless node, so it's filtered out
    # rather than cluttering what's meant to be a call/import graph.
    py_filepaths = {fp for fp in id_to_filepath.values() if fp and fp.endswith(".py")}
    filepaths = sorted(py_filepaths)

    edges: set[tuple[str, str, str]] = set()
    for comp_type in ("calls", "imports"):
        df = registrar.get(comp_type).to_pandas()
        if df.empty or "value_eid" not in df.columns:
            continue
        for _, row in df.dropna(subset=["value_eid"]).iterrows():
            src_fp = id_to_filepath.get(row["entity_id"])
            dst_fp = id_to_filepath.get(row["value_eid"])
            if (
                src_fp and dst_fp and src_fp != dst_fp
                and src_fp in py_filepaths and dst_fp in py_filepaths
            ):
                edges.add((src_fp, dst_fp, comp_type))

    return {
        "nodes": [{"id": fp, "label": _file_node_label(fp)} for fp in filepaths],
        "edges": [
            {"source": s, "target": t, "kind": k} for s, t, k in sorted(edges)
        ],
    }


def render_mermaid(graph: dict, direction: str = "LR") -> str:
    """Render a ``{"nodes", "edges"}`` graph (as returned by ``build_architecture_graph``) as Mermaid.

    Solid arrows are ``calls`` edges, dashed arrows are ``imports`` edges.
    Node ids are remapped to short ``n0``, ``n1``, ... identifiers since a
    raw filepath contains characters (``/``, ``.``) Mermaid node IDs can't.

    Args:
        graph: A graph dict as returned by ``build_architecture_graph``.
        direction: Mermaid flowchart direction (default left-to-right).

    Returns:
        Mermaid ``flowchart`` source text.
    """
    lines = [f"flowchart {direction}"]
    if not graph["nodes"]:
        lines.append('    empty["(no entities found)"]')
        return "\n".join(lines)

    id_map = {n["id"]: f"n{i}" for i, n in enumerate(graph["nodes"])}
    for n in graph["nodes"]:
        label = n["label"].replace('"', "'")
        lines.append(f'    {id_map[n["id"]]}["{label}"]')
    for e in graph["edges"]:
        arrow = "-.->" if e["kind"] == "imports" else "-->"
        lines.append(f'    {id_map[e["source"]]} {arrow} {id_map[e["target"]]}')
    return "\n".join(lines)


def _qualified_label(path: str, filepath: str | None) -> str:
    """Strip an entity path's ``{filepath}:`` and module-dotted prefix, keeping any class nesting.

    E.g. ``path='story_simulator/resolve.py:story_simulator.resolve.TurnReplay.resolve'``,
    ``filepath='story_simulator/resolve.py'`` -> ``'TurnReplay.resolve'`` -- the
    module prefix is redundant once the node already sits inside that
    file's own subgraph, but a class name in between is exactly the "class
    architecture" grouping information worth keeping in the label.
    """
    dotted = path.split(":", 1)[-1]
    if not filepath:
        return dotted
    module_name = ".".join(Path(filepath).with_suffix("").parts)
    if dotted == module_name:
        return module_name.rsplit(".", 1)[-1]
    prefix = module_name + "."
    return dotted[len(prefix):] if dotted.startswith(prefix) else dotted


def build_call_reachability(registrar: Registrar, root: str, max_depth: int | None = None) -> dict:
    """BFS the entity-level ``calls`` graph outward from ``root``, uncollapsed.

    Unlike ``build_architecture_graph`` (one node per file, same-file edges
    dropped as uninformative at that granularity), this keeps every entity
    as its own node and keeps every call edge including within the same
    file -- the point here is exactly the fine-grained "what does this one
    entry point actually call, and what does that call" trace the overview
    graph deliberately doesn't show. Traversal only ever follows resolved
    edges (a call to something undocumented or third-party has nowhere to
    go), so it terminates even with no ``max_depth`` given; a cycle is
    recorded as an edge back to an already-visited node rather than
    re-expanded.

    Args:
        registrar: A Registrar (or Registry) with loaded registry data.
        root: An entity hash, alias, or path substring identifying the
            starting entity, resolved via ``candidate_entity_ids`` -- the
            same resolution any other entity_ref field in iacs uses.
        max_depth: Maximum number of call hops to follow outward from
            root. None (the default) follows every reachable entity.

    Returns:
        ``{"root": entity_id, "nodes": [{"id", "label", "filepath"}, ...],
        "edges": [{"source": entity_id, "target": entity_id}, ...]}``.

    Raises:
        ValueError: If ``root`` doesn't resolve to exactly one entity.
    """
    entity_id_df = registrar.get("entity_id").to_pandas()
    candidates = candidate_entity_ids(root, entity_id_df)
    if len(candidates) != 1:
        raise ValueError(
            f"root {root!r} resolved to {len(candidates)} entities, expected exactly 1: {candidates}"
        )
    root_eid = candidates[0]

    id_to_path = entity_id_df.set_index("value")["path"].to_dict() if "path" in entity_id_df.columns else {}
    id_to_filepath = (
        entity_id_df.set_index("value")["filepath"].to_dict() if "filepath" in entity_id_df.columns else {}
    )

    # A call target only ever means something once resolved to a .py-sourced
    # entity -- Python code never calls a YAML-described requirement or
    # schema entity, so a resolved-but-non-.py target (e.g. a bare `float(...)`
    # builtin call coincidentally alias-matching iacs's own `float`
    # schema-type entity in builtins/components.yaml) is a false positive
    # of substring/alias resolution, not a real edge, and is dropped here.
    calls_df = registrar.get("calls").to_pandas()
    adjacency: dict[str, list[str]] = {}
    if not calls_df.empty and "value_eid" in calls_df.columns:
        for _, row in calls_df.dropna(subset=["value_eid"]).iterrows():
            target = row["value_eid"]
            target_fp = id_to_filepath.get(target)
            if target_fp and target_fp.endswith(".py"):
                adjacency.setdefault(row["entity_id"], []).append(target)

    visited = {root_eid}
    order = [root_eid]
    edges: list[tuple[str, str]] = []
    frontier = [root_eid]
    depth = 0
    while frontier and (max_depth is None or depth < max_depth):
        next_frontier = []
        for node in frontier:
            for target in sorted(set(adjacency.get(node, []))):
                edges.append((node, target))
                if target not in visited:
                    visited.add(target)
                    order.append(target)
                    next_frontier.append(target)
        frontier = next_frontier
        depth += 1

    nodes = [
        {
            "id": eid,
            "label": _qualified_label(id_to_path.get(eid, eid), id_to_filepath.get(eid)),
            "filepath": id_to_filepath.get(eid),
        }
        for eid in order
    ]
    return {
        "root": root_eid,
        "nodes": nodes,
        "edges": [{"source": s, "target": t} for s, t in edges],
        "call_sequences": _call_sequences(calls_df, edges),
    }


def _call_sequences(calls_df, edges: list[tuple[str, str]]) -> list[dict]:
    """Group ``edges`` (``build_call_reachability``'s own already-correctly-
    scoped (caller, target) pairs -- right depth, right resolution, no
    caller beyond ``max_depth`` sneaking back in) by caller, each group's
    targets ordered by ``load_python``'s ``seq`` field on ``calls`` where
    available.

    Grouping from ``edges`` rather than re-deriving from ``calls_df`` and a
    raw "visited" set is what keeps this consistent with the BFS's own
    depth cutoff: a node added to ``visited`` but never actually expanded
    (stopped by ``max_depth``) contributes no edges, so it contributes no
    sequence either, automatically -- no separate bookkeeping needed here.

    Args:
        calls_df: The raw ``calls`` component table (as loaded by
            ``registrar.get("calls").to_pandas()``).
        edges: ``(source, target)`` pairs, as computed by
            ``build_call_reachability``'s own BFS.

    Returns:
        ``[{"caller": entity_id, "targets": [entity_id, ...]}, ...]``, one
        entry per distinct caller in ``edges``. ``targets`` always has at
        least one entry (a caller with no edges contributes nothing) and
        never repeats one immediately after itself.
    """
    call_order: dict[tuple[str, str], object] = {}
    if not calls_df.empty and "value_eid" in calls_df.columns and "seq" in calls_df.columns:
        for _, row in calls_df.dropna(subset=["value_eid"]).iterrows():
            call_order[(row["entity_id"], row["value_eid"])] = row["seq"]

    by_caller: dict[str, list[str]] = {}
    for caller, target in edges:
        by_caller.setdefault(caller, []).append(target)

    sequences = []
    for caller, targets in by_caller.items():
        ordered = sorted(targets, key=lambda t: call_order.get((caller, t), float("inf")))
        deduped = [t for i, t in enumerate(ordered) if i == 0 or t != ordered[i - 1]]
        sequences.append({"caller": caller, "targets": deduped})
    return sequences


def render_reachability_mermaid(graph: dict, direction: str = "TB") -> str:
    """Render a ``build_call_reachability`` graph as Mermaid, one subgraph per source file.

    The root node gets a distinct fill via a Mermaid ``rootNode`` class, so
    it stays visually anchored regardless of how large the reachable set
    grows.

    A caller with two or more resolved call targets (see
    ``build_call_reachability``'s ``call_sequences``) gets its targets
    drawn as their own ``seqN`` subgraph instead of scattered across their
    usual per-file ones -- internally chained by dotted "A then B" arrows
    in call order, with a single solid arrow from the caller to the
    subgraph as a whole. Fanning N solid arrows out from one caller *and*
    N-1 dotted arrows threading back through the same targets said the
    same thing twice and read as clutter, not structure; one arrow in, one
    visibly-ordered box, says it once. A caller with only one call target
    keeps the plain direct arrow -- there is no order to show.

    A sequence subgraph deliberately declares no explicit inner
    ``direction`` of its own -- it inherits the outer flowchart's, so
    ``direction="TB"``'s default keeps a box's multi-step chain readable
    top-to-bottom without any inner override. This isn't a style choice:
    Mermaid/dagre's compound layout mis-anchors an edge that crosses a
    subgraph boundary when that subgraph declares its own explicit
    ``direction`` statement -- confirmed by a minimal repro (a 5-node
    chain in a box, with the box's first member also targeted by an edge
    from outside) where the boundary-crossing edge rendered as if it
    started from an arbitrary internal node instead of the true source,
    regardless of whether the inner direction matched or mismatched the
    outer one. Only omitting the inner ``direction`` line entirely fixed
    it. An overall left-right diagram would need its boxes to run
    left-right too for that same reason, which cramps a multi-step chain
    into one band -- top-to-bottom is the direction that both avoids the
    dagre bug and stays legible for a vertical chain, so it's the only
    supported combination here.

    Only the *target* side gets this box treatment, not the source: an
    outgoing edge from a node that happens to live inside some other
    caller's box (e.g. ``_resolve_args`` is a target inside
    ``advance_simulation``'s box, and also its own caller elsewhere)
    still starts from that specific node, not the box's boundary -- which
    member actually made the call is real information, worth keeping
    visible rather than collapsing into "the box, generically." An
    *incoming* edge, though, does get the box treatment: "something
    outside calls into this whole ordered sequence" is what the box
    exists to show, and there's no member-level provenance to lose by
    landing the arrow on the boundary instead of the specific first-called
    node.

    Missing ``call_sequences`` entirely (e.g. an older or hand-built graph
    dict) falls back to one plain arrow per ``edges`` entry, for backward
    compatibility with that input shape.

    Args:
        graph: A graph dict as returned by ``build_call_reachability``.
        direction: Mermaid flowchart direction for the overall diagram
            (default top-to-bottom -- see above for why this is the only
            direction that avoids the dagre boundary-crossing-edge bug
            while keeping a sequence box's internal chain legible).

    Returns:
        Mermaid ``flowchart`` source text.
    """
    # Transparent cluster backgrounds were tried here as part of tracking
    # down a boundary-crossing-edge rendering bug (see this function's own
    # docstring above for the actual root cause and fix -- an explicit
    # inner `direction` on a sequence subgraph). Once that was found and
    # fixed, the transparency workaround wasn't needed for correctness
    # anymore, so it's gone too -- default Mermaid theme.
    lines = [f"flowchart {direction}"]
    if not graph["nodes"]:
        lines.append('    empty["(root not found)"]')
        return "\n".join(lines)

    id_map = {n["id"]: f"n{i}" for i, n in enumerate(graph["nodes"])}
    label_by_id = {n["id"]: n["label"].replace('"', "'") for n in graph["nodes"]}

    call_sequences = graph.get("call_sequences")
    sequence_members: dict[str, str] = {}
    sequence_box_of_caller: dict[str, str] = {}
    sequence_lines: list[str] = []
    solid_edges: list[tuple[str, str]] = []

    if call_sequences is not None:
        # Pass 1: lay out every 2+-target caller's own box, and record
        # which box (if any) each node ends up inside -- needed before
        # pass 2 can resolve any edge's endpoints, since a caller earlier
        # in call_sequences may itself be a later caller's box member (or
        # vice versa).
        for i, seq in enumerate(call_sequences):
            caller, targets = seq["caller"], seq["targets"]
            if len(targets) < 2:
                continue
            seq_id = f"seq{i}"
            sequence_box_of_caller[caller] = seq_id
            sequence_lines.append(f'    subgraph {seq_id}["{label_by_id.get(caller, caller)}"]')
            for t in targets:
                sequence_members[t] = seq_id
                sequence_lines.append(f'        {id_map[t]}["{label_by_id.get(t, t)}"]')
            for a, b in zip(targets, targets[1:]):
                sequence_lines.append(f'        {id_map[a]} -.-> {id_map[b]}')
            sequence_lines.append("    end")

        # Pass 2: the source is always the caller's own specific node --
        # never abstracted to a box, even when the caller is itself a
        # member of one (see this function's own docstring for why). The
        # target resolves to the box it's a *member* of (`sequence_members`,
        # i.e. it's a target inside someone else's sequence) when it has
        # one, or the caller's own brand-new box for a 2+-target sequence,
        # falling back to the plain node id otherwise.
        for seq in call_sequences:
            caller, targets = seq["caller"], seq["targets"]
            source_ref = id_map[caller]
            if len(targets) >= 2:
                solid_edges.append((source_ref, sequence_box_of_caller[caller]))
            else:
                for t in targets:
                    target_ref = sequence_members.get(t, id_map[t])
                    solid_edges.append((source_ref, target_ref))
    else:
        for e in graph.get("edges", []):
            solid_edges.append((id_map[e["source"]], id_map[e["target"]]))

    by_file: dict[str, list[dict]] = {}
    for n in graph["nodes"]:
        if n["id"] in sequence_members:
            continue
        by_file.setdefault(n["filepath"] or "(unknown)", []).append(n)

    for i, (filepath, nodes) in enumerate(sorted(by_file.items())):
        subgraph_label = _module_label(filepath) if filepath.endswith(".py") else filepath
        lines.append(f'    subgraph sg{i}["{subgraph_label}"]')
        for n in nodes:
            lines.append(f'        {id_map[n["id"]]}["{label_by_id[n["id"]]}"]')
        lines.append("    end")

    lines.extend(sequence_lines)

    # Defensive rather than commonly triggered: the source side is always
    # a specific node, so two different callers sharing a target's box
    # never collapse into "the same" edge -- but a single caller calling
    # the same target twice non-consecutively would still
    # produce the identical pair twice, so dedupe (order-preserving)
    # rather than draw parallel copies of it. A same-box self-reference
    # (two members of one box calling each other) is dropped too -- it
    # says nothing an arrow drawn back onto the same box's boundary can
    # usefully convey.
    for s, t in dict.fromkeys(solid_edges):
        if s != t:
            lines.append(f'    {s} --> {t}')

    lines.append(f'    class {id_map[graph["root"]]} rootNode')
    lines.append("    classDef rootNode fill:#f96,stroke:#333,stroke-width:3px")
    return "\n".join(lines)
