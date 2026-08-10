"""View helpers for building a file-level architecture graph from parsed Python source.

Aggregates the ``calls``/``imports`` entity_ref relations that
``iacs.dataflows.etl.load_python`` extracts (module/class/function calls and
imports, resolved to target entities where the target is itself a
qualifying entity -- see that module's ``_make_components``) into a
deduplicated, file-to-file graph and a Mermaid flowchart rendering of it.
"""

from iacs.registrar import Registrar


def _module_label(filepath: str) -> str:
    """Short readable label for a source filepath, e.g. 'iacs/registrar.py' -> 'registrar'."""
    stem = filepath.rsplit("/", 1)[-1]
    return stem[:-3] if stem.endswith(".py") else stem


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
        "nodes": [{"id": fp, "label": _module_label(fp)} for fp in filepaths],
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
