"""Core command logic shared between the MCP server and CLI."""
from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from iacs.architect import Architect

MANIFEST_ENV_VAR = "IACS_MANIFEST"
EXAMPLE_MANIFEST = Path(__file__).parent.parent / "examples" / "example"
BUILTINS_DIR = Path(__file__).parent / "builtins"
IACS_MANIFEST_DIR = Path(__file__).parent / "iacs_manifest"


def parse_manifest_env() -> list[str]:
    """Return manifest paths from the environment variable, or the built-in example."""
    raw = os.environ.get(MANIFEST_ENV_VAR)
    if not raw:
        return [str(EXAMPLE_MANIFEST)]
    return [p.strip() for p in raw.split(os.pathsep) if p.strip()]


def get_manifest_path_str(manifest_paths: list[str] | None = None) -> str:
    """Format manifest path info as a human-readable string.

    If ``manifest_paths`` is given, report those paths (e.g. from --manifest).
    Otherwise read from the environment variable or fall back to the built-in example.
    """
    if manifest_paths is not None:
        paths_str = ", ".join(repr(p) for p in manifest_paths)
        return f"Manifest path(s): {paths_str} (from --manifest argument)"
    raw = os.environ.get(MANIFEST_ENV_VAR)
    if raw:
        paths = [p.strip() for p in raw.split(os.pathsep) if p.strip()]
        source = f"from {MANIFEST_ENV_VAR} environment variable"
    else:
        paths = [str(EXAMPLE_MANIFEST)]
        source = f"built-in default (set {MANIFEST_ENV_VAR} to override)"
    paths_str = ", ".join(repr(p) for p in paths)
    return f"Manifest path(s): {paths_str} ({source})"


def make_architect(manifest_paths: list[str]) -> "Architect":
    """Create an Architect loaded from the given manifest directory paths."""
    from iacs.architect import Architect
    return Architect.from_manifest(manifest_paths)


def cmd_list_component_types(arch: "Architect") -> str:
    """Return a summary of loaded and available-but-ungenerated component types."""
    loaded = arch.registry.component_types
    audit_map = available_audit_components()
    unloaded = {ct: df for ct, df in audit_map.items() if ct not in loaded}
    lines = [f"Loaded component types: {loaded}"]
    if unloaded:
        lines.append("\nAvailable audit components (not yet generated):")
        for comp_type, dataflow in unloaded.items():
            lines.append(f"  - {comp_type}: run run_dataflow('{dataflow}') to generate")
    return "\n".join(lines)


def cmd_view_component(arch: "Architect", component_type: str, format: str = "csv") -> str:
    """Return all data for a component type as CSV or markdown."""
    df = arch.registry.view_df(component_type).reset_index()
    if format == "markdown":
        return df.to_markdown(index=False)
    return df.to_csv(index=False)


def cmd_view_entity(arch: "Architect", entity_id: str, format: str = "markdown") -> str:
    """Return all component data for a specific entity."""
    return arch.registry.view_entity(entity_id, format=format)


def cmd_run_dataflow(arch: "Architect", name: str) -> str:
    """Execute a dataflow, returning a status string listing any new component types."""
    before = set(arch.registry.component_types)
    arch.execute(name)
    after = set(arch.registry.component_types)
    added = sorted(after - before)
    if added:
        return f"Dataflow {name!r} complete. New component types: {added}"
    return f"Dataflow {name!r} complete. No new component types added."


def cmd_refresh(arch: "Architect") -> str:
    """Run the ETL export and write normalised YAML back to the original source paths.

    Executes the etl.export_manifest dataflow against the already-loaded
    registry (which has gone through load → validate → derive) and saves
    each file to its original location, effectively round-tripping the
    manifest through the pipeline.
    """
    result = arch.execute("etl.export_manifest")
    saved: list[str] = result.get("exported_manifest_filepaths", [])
    if not saved:
        return "No EC files to refresh."
    lines = [f"Refreshed {len(saved)} file(s):"]
    lines.extend(f"  {p}" for p in saved)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Format guide helpers
# ---------------------------------------------------------------------------

def _get_description(component_list: list) -> str:
    for item in component_list:
        if isinstance(item, dict) and "description" in item:
            return str(item["description"]).strip()
    return ""


def _format_field_entry(field_name: str, meta: dict) -> str:
    line = f"- {field_name}"
    ftype = meta.get("type")
    if ftype:
        line += f": {ftype}"
    extras = []
    if meta.get("nullable") is False:
        extras.append("required")
    default = meta.get("default")
    if default is not None:
        extras.append(f"default: {default}")
    frange = meta.get("range")
    if frange is not None:
        extras.append(f"range: {frange}")
    if extras:
        line += f" ({', '.join(str(e) for e in extras)})"
    fdesc = meta.get("description")
    if fdesc:
        line += f" — {str(fdesc).strip()}"
    return line


def _extract_component_spec(comp_name: str, comp_list: list) -> str:
    desc = _get_description(comp_list)
    lines = [f"### {comp_name}", desc]
    field_lines = []
    for item in comp_list:
        if not isinstance(item, dict) or "field" not in item:
            continue
        field_val = item["field"]
        if not isinstance(field_val, dict):
            continue
        is_schema_case = (
            all(isinstance(v, (dict, type(None))) for v in field_val.values())
            and any(isinstance(v, dict) for v in field_val.values())
        )
        if is_schema_case:
            for fname, fmeta in field_val.items():
                if isinstance(fmeta, dict):
                    field_lines.append("  " + _format_field_entry(fname, fmeta))
        else:
            fname = field_val.get("value", "value")
            meta = {k: v for k, v in field_val.items() if k != "value"}
            field_lines.append("  " + _format_field_entry(fname, meta))
    if field_lines:
        lines.append("Fields:")
        lines.extend(field_lines)
    return "\n".join(lines)


def build_format_description() -> str:
    """Assemble the format guide string from builtins YAML files."""
    guide_data = yaml.safe_load(
        (IACS_MANIFEST_DIR / "format_guide.yaml").read_text(encoding="utf-8")
    )
    comp_data = yaml.safe_load(
        (BUILTINS_DIR / "components.yaml").read_text(encoding="utf-8")
    )

    fmt = guide_data["entity_first_yaml_format"]
    intro = _get_description(fmt.get("data", []))
    rules = _get_description(fmt.get("format_rules", []))
    example = _get_description(fmt.get("canonical_example", []))

    iacs_comp = comp_data.get("iacs_component", {})
    comp_sections: list[str] = []

    def _collect_specs(mapping: dict) -> None:
        for comp_name, comp_val in mapping.items():
            if comp_name == "data":
                continue
            if isinstance(comp_val, list):
                comp_sections.append(_extract_component_spec(comp_name, comp_val))
            elif isinstance(comp_val, dict):
                if "data" in comp_val and isinstance(comp_val["data"], list):
                    comp_sections.append(_extract_component_spec(comp_name, comp_val["data"]))
                _collect_specs({k: v for k, v in comp_val.items() if k != "data"})

    _collect_specs(iacs_comp)

    ds = comp_data.get("data_structure", {})
    if isinstance(ds.get("field"), list):
        comp_sections.append(_extract_component_spec("field", ds["field"]))

    comp_ref = "\n\n".join(comp_sections)
    return "\n\n".join([
        f"# Entity-First YAML Format\n\n{intro}",
        f"## Format Rules\n\n{rules}",
        f"## Built-in Component Types\n\n{comp_ref}",
        f"## Canonical Example\n\n{example}",
    ])


def validate_yaml_string(yaml_string: str) -> str:
    """Parse and validate entity-first YAML, returning a result message."""
    try:
        yaml.safe_load(yaml_string)
    except yaml.YAMLError as exc:
        return f"YAML syntax error:\n{exc}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        yaml_file = Path(tmp_dir) / "input.yaml"
        yaml_file.write_text(yaml_string, encoding="utf-8")
        try:
            from iacs.architect import Architect
            arch = Architect.from_manifest(tmp_dir)
        except Exception:
            return f"Validation error:\n{traceback.format_exc()}"

    types = arch.registry.component_types
    return f"Valid. Component types found: {types}"


def available_audit_components() -> dict[str, str]:
    """Return a mapping of audit component type name to its run_dataflow argument."""
    comp_data = yaml.safe_load(
        (BUILTINS_DIR / "components.yaml").read_text(encoding="utf-8")
    )
    audit_section = comp_data.get("iacs_component", {}).get("audit", {})
    return {
        key: f"audit.{key}"
        for key in audit_section
        if key != "data"
    }
