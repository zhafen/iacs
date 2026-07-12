"""Generate Hamilton DAG images for documentation.

Discovers all Hamilton-compatible modules under iacs.dataflows, generates PNG
DAG visualizations, and writes docs/dataflows/index.md to match.

Subdags are rendered as single collapsed nodes (bold border) rather than
expanding their internal constituents.

Run via: uv run python docs/gen_dag_images.py
Images are written to docs/dataflows/img/.
"""

import importlib
import pkgutil
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import iacs.dataflows  # noqa: E402
from hamilton import driver  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "dataflows" / "img"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = Path(__file__).parent / "dataflows" / "index.md"

_BASE_PKG = "iacs.dataflows"


def _discover_modules():
    """Yield (module_path, short_name) for every non-package module under iacs.dataflows."""
    for _finder, module_path, ispkg in pkgutil.walk_packages(
        iacs.dataflows.__path__, prefix=_BASE_PKG + "."
    ):
        if not ispkg:
            short = module_path.removeprefix(_BASE_PKG + ".")
            yield module_path, short


def _collapsed_graph(dr) -> "graphviz.Digraph":
    """Build a graphviz graph with subdags collapsed to single bold-border nodes.

    A node is "top-level" if its name contains no dot (subdag-internal nodes are
    named ``outer.inner`` by Hamilton).  Edges are derived by finding every
    cross-subdag dependency in the full graph and mapping it back to the
    owning top-level node on each side.
    """
    import graphviz

    all_nodes = dr.graph.nodes
    top_level = {n for n in all_nodes if "." not in n}

    def owner(name: str) -> str:
        return name.split(".")[0]

    edges: set[tuple[str, str]] = set()
    for name, node in all_nodes.items():
        own = owner(name)
        for dep in node.dependencies:
            dep_own = owner(dep.name)
            if dep_own != own and dep_own in top_level and own in top_level:
                edges.add((dep_own, own))

    dot = graphviz.Digraph()
    dot.attr(rankdir="LR", ranksep="0.4", concentrate="true")

    for name in sorted(top_level):
        node = all_nodes[name]
        is_subdag = any(n.startswith(name + ".") for n in all_nodes)
        is_input = not node.dependencies

        typ = node.type
        type_str = getattr(typ, "__name__", str(typ)).split(".")[-1]
        label = f"<<b>{name}</b><br/><br/><i>{type_str}</i>>"

        attrs = dict(
            label=label,
            fontname="Helvetica",
            margin="0.15",
            shape="rectangle",
            style="rounded,filled",
            fillcolor="#ffffff" if is_input else "#b4d8e4",
        )
        if is_subdag:
            attrs["penwidth"] = "3"

        dot.node(name, **attrs)

    for src, dst in sorted(edges):
        dot.edge(src, dst)

    return dot


def _generate_dag_image(module_path: str, short_name: str) -> Path | None:
    try:
        mod = importlib.import_module(module_path)
        dr = driver.Builder().with_modules(mod).build()
        filename = short_name.replace(".", "_")
        output_path = OUTPUT_DIR / f"{filename}.png"
        _collapsed_graph(dr).render(str(output_path.with_suffix("")), format="png", cleanup=True)
        print(f"  Generated: {output_path.name}")
        return output_path
    except Exception as exc:
        print(f"  Skipped {module_path}: {exc}")
        return None


_TOP_LEVEL_GROUP = "(top-level)"

# Pipeline order: base_etl composes etl -> validation -> derive -> validation,
# then audits run last, consuming the final validated registry.
_GROUP_ORDER = [_TOP_LEVEL_GROUP, "etl", "validation", "derive", "audit"]


def _group(short_name: str) -> str:
    """The dataflow subpackage a module belongs to, mirroring iacs/dataflows/ on disk."""
    if "." not in short_name:
        return _TOP_LEVEL_GROUP
    return short_name.rsplit(".", 1)[0]


def _generate_index(entries: list[tuple[str, str]]) -> None:
    lines = [
        "# Dataflow DAGs\n\n",
        "Hamilton DAG visualizations for iacs dataflows, grouped by the\n",
        "subpackage each module lives in under `iacs/dataflows/` and ordered\n",
        "to reflect the order in which they run.\n",
        "Regenerate with: `uv run python docs/gen_dag_images.py`\n\n",
    ]

    groups: dict[str, list[tuple[str, str]]] = {}
    for module_path, short_name in entries:
        groups.setdefault(_group(short_name), []).append((module_path, short_name))

    def _group_key(g: str) -> tuple[int, str]:
        try:
            return (_GROUP_ORDER.index(g), "")
        except ValueError:
            return (len(_GROUP_ORDER), g)

    ordered_groups = sorted(groups, key=_group_key)
    for group_index, group in enumerate(ordered_groups):
        if group_index > 0:
            lines.append("---\n\n")
        heading = "Top-level" if group == _TOP_LEVEL_GROUP else f"`{group}/`"
        lines.append(f"## {heading}\n\n")
        for module_path, short_name in sorted(groups[group], key=lambda e: e[1]):
            filename = short_name.replace(".", "_")
            lines.append(f"### `{short_name}`\n\n")
            lines.append(f"![{short_name} DAG](img/{filename}.png)\n\n")

    INDEX_PATH.write_text("".join(lines))
    print(f"  Updated {INDEX_PATH.name}")


for stale in OUTPUT_DIR.glob("*.png"):
    stale.unlink()
    print(f"  Removed stale: {stale.name}")

print("Generating Hamilton DAG images...")
generated: list[tuple[str, str]] = []
for module_path, short_name in sorted(_discover_modules()):
    if _generate_dag_image(module_path, short_name) is not None:
        generated.append((module_path, short_name))

_generate_index(generated)
print(f"Done. {len(generated)} DAG(s) generated.")
