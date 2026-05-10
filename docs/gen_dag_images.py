"""Script to generate Hamilton DAG images for documentation.

Run via: uv run python docs/gen_dag_images.py
Images are written to docs/dataflows/img/.
"""

import importlib
import sys
from pathlib import Path

# Ensure the project root is on the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from hamilton import driver

OUTPUT_DIR = Path(__file__).parent / "dataflows" / "img"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATAFLOWS = [
    ("iacs.dataflows.etl.load_manifest", "load_manifest"),
    ("iacs.dataflows.etl.derive_components", "derive_components"),
    ("iacs.dataflows.etl.export_manifest", "export_manifest"),
    ("iacs.dataflows.validation.validate_registry", "validate_registry"),
    ("iacs.dataflows.base_etl", "base_etl"),
    ("iacs.dataflows.audit.requirement_coverage", "audit_requirement_coverage"),
    ("iacs.dataflows.audit.traceability", "audit_traceability"),
    ("iacs.dataflows.audit.todo", "audit_todo"),
]


def generate_dag_image(module_path: str, name: str) -> Path | None:
    try:
        mod = importlib.import_module(module_path)
        dr = driver.Builder().with_modules(mod).build()
        output_path = OUTPUT_DIR / f"{name}.png"
        dr.display_all_functions(output_path, render_kwargs={"format": "png"})
        print(f"  Generated: {output_path}")
        return output_path
    except Exception as exc:
        print(f"  WARNING: Could not generate DAG for {module_path}: {exc}")
        return None


print("Generating Hamilton DAG images...")
for module_path, name in DATAFLOWS:
    generate_dag_image(module_path, name)
print("Done.")
