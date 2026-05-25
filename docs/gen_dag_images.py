"""Generate Hamilton DAG images for documentation.

Discovers all Hamilton-compatible modules under iacs.dataflows, generates PNG
DAG visualizations, and writes docs/dataflows/index.md to match.

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


def _generate_dag_image(module_path: str, short_name: str) -> Path | None:
    try:
        mod = importlib.import_module(module_path)
        dr = driver.Builder().with_modules(mod).build()
        filename = short_name.replace(".", "_")
        output_path = OUTPUT_DIR / f"{filename}.png"
        dr.display_all_functions(output_path, render_kwargs={"format": "png"})
        print(f"  Generated: {output_path.name}")
        return output_path
    except Exception as exc:
        print(f"  Skipped {module_path}: {exc}")
        return None


def _generate_index(entries: list[tuple[str, str]]) -> None:
    lines = [
        "# Dataflow DAGs\n\n",
        "Hamilton DAG visualizations for iacs dataflows.\n",
        "Regenerate with: `uv run python docs/gen_dag_images.py`\n\n",
    ]
    for module_path, short_name in entries:
        filename = short_name.replace(".", "_")
        lines.append(f"---\n\n## `{short_name}`\n\n")
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
