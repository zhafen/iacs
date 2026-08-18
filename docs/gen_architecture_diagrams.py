"""Generate a Mermaid architecture diagram for iacs's own file/call structure.

Self-documents iacs the same way gen_dag_images.py does for its Hamilton
dataflows: parses iacs's own package source (via
emc2p.dataflows.etl.load_python, driven through a full Registrar load) into
entities, then collapses their calls/imports relations into a file-level
Mermaid flowchart -- solid arrows for calls, dashed arrows for imports.

Run via: uv run python docs/gen_architecture_diagrams.py
Written to docs/architecture/index.md.
"""

from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from iacs.registrar import Registrar  # noqa: E402
from iacs.views.architecture_graph import build_architecture_graph, render_mermaid  # noqa: E402

OUTPUT_PATH = Path(__file__).parent / "architecture" / "index.md"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

print("Generating architecture diagram...")
reg = Registrar.from_manifest([str(project_root / "iacs")])
graph = build_architecture_graph(reg)
mermaid = render_mermaid(graph)

content = (
    "# Architecture\n\n"
    "File-level call/import structure of iacs's own codebase, parsed from "
    "source the same way `emc2p.dataflows.etl.load_python` parses any "
    "project's code -- solid arrows are function/method calls, dashed "
    "arrows are imports. Only entities with a docstring or `__iacs__` "
    "metadata become graph-relevant (see that module's own docstring for "
    "why undocumented helpers are deliberately excluded); a file with none "
    "of its own still shows up if something documented elsewhere calls "
    "into it.\n\n"
    "Regenerate with: `uv run python docs/gen_architecture_diagrams.py`\n\n"
    f"```mermaid\n{mermaid}\n```\n"
)
OUTPUT_PATH.write_text(content)
print(
    f"  Generated: {OUTPUT_PATH.relative_to(project_root)} "
    f"({len(graph['nodes'])} nodes, {len(graph['edges'])} edges)"
)
