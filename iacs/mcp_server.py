"""MCP server exposing iacs registry tools."""

import os
import tempfile
import traceback
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

server = FastMCP("iacs")

_BUILTIN_MANIFEST = Path(__file__).parent.parent / "examples" / "example"
_BUILTINS_DIR = Path(__file__).parent.parent / "builtins"

_architect: Architect | None = None


def _get_architect() -> Architect:
    global _architect
    if _architect is None:
        manifest = os.environ.get("IACS_MANIFEST", str(_BUILTIN_MANIFEST))
        _architect = Architect.from_manifest(manifest)
    return _architect


# ---------------------------------------------------------------------------
# Format guide helpers
# ---------------------------------------------------------------------------

def _get_description(component_list: list) -> str:
    """Return the value of the first description component in a list."""
    for item in component_list:
        if isinstance(item, dict) and "description" in item:
            return str(item["description"]).strip()
    return ""


def _format_field_entry(field_name: str, meta: dict) -> str:
    """Format a single field definition as a readable line."""
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
    """Build a human-readable spec block for one iacs component type."""
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


def _build_format_description() -> str:
    """Assemble the format guide string from builtins YAML files.

    Reads format rules and a canonical example from format_guide.yaml, then
    builds a component reference from the iacs_component and data_structure
    sections of components.yaml.
    """
    guide_data = yaml.safe_load(
        (_BUILTINS_DIR / "format_guide.yaml").read_text(encoding="utf-8")
    )
    comp_data = yaml.safe_load(
        (_BUILTINS_DIR / "components.yaml").read_text(encoding="utf-8")
    )

    fmt = guide_data["entity_first_yaml_format"]
    intro = _get_description(fmt.get("data", []))
    rules = _get_description(fmt.get("format_rules", []))
    example = _get_description(fmt.get("canonical_example", []))

    iacs_comp = comp_data.get("iacs_component", {})
    comp_sections = []

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


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def _validate_yaml_string(yaml_string: str) -> str:
    """Parse and validate entity-first YAML, returning a result message.

    Writes the YAML to a temporary file and runs it through the full
    Architect pipeline. Returns a success message listing component types
    found, or an error message describing what went wrong.
    """
    try:
        yaml.safe_load(yaml_string)
    except yaml.YAMLError as exc:
        return f"YAML syntax error:\n{exc}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        yaml_file = Path(tmp_dir) / "input.yaml"
        yaml_file.write_text(yaml_string, encoding="utf-8")
        try:
            arch = Architect.from_manifest(tmp_dir)
        except Exception:
            return f"Validation error:\n{traceback.format_exc()}"

    types = arch.registry.component_types
    return f"Valid. Component types found: {types}"


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@server.tool()
def load_manifest(manifest_path: str) -> str:
    """Load an iacs manifest from a directory path, replacing the current registry.

    Args:
        manifest_path: Path to the manifest directory.
    """
    global _architect
    _architect = Architect.from_manifest(manifest_path)
    types = _architect.registry.component_types
    return f"Loaded manifest from {manifest_path!r}. Component types: {types}"


@server.tool()
def list_component_types() -> list[str]:
    """List all component types available in the iacs registry."""
    return _get_architect().registry.component_types


@server.tool()
def view_component(component_type: str, format: str = "csv") -> str:
    """Return all data for a component type.

    Args:
        component_type: The name of the component type to view.
        format: Output format — "csv" (default) or "markdown" for a
            human-readable table.
    """
    arch = _get_architect()
    df = arch.registry.view_df(component_type).reset_index()
    if format == "markdown":
        return df.to_markdown(index=False)
    return df.to_csv(index=False)


@server.tool()
def describe_format() -> str:
    """Return the entity-first YAML format specification with a canonical example.

    Use this before transcribing text into iacs YAML to understand the
    required structure, built-in component types, and formatting rules.
    Sourced from the iacs builtins directory.
    """
    return _build_format_description()


@server.tool()
def validate_yaml(yaml_string: str) -> str:
    """Validate entity-first YAML and report any errors.

    Parses the YAML string, then runs it through the full iacs pipeline
    (load → validate → derive). Returns a success message listing the
    component types found, or a detailed error message.

    Args:
        yaml_string: Raw YAML text in entity-first format.
    """
    return _validate_yaml_string(yaml_string)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
