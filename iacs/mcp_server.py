"""MCP server exposing iacs registry tools."""
from __future__ import annotations

import os
import tempfile
import traceback
import weakref
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from iacs.architect import Architect

_MANIFEST_ENV_VAR = "IACS_MANIFEST"
_EXAMPLE_MANIFEST = Path(__file__).parent.parent / "examples" / "example"
_BUILTINS_DIR = Path(__file__).parent / "builtins"
_IACS_MANIFEST_DIR = Path(__file__).parent / "iacs_manifest"

_architects: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _get_architect(ctx: Context) -> Architect:
    session = ctx.request_context.session
    if session not in _architects:
        from iacs.architect import Architect
        manifest = os.environ.get(_MANIFEST_ENV_VAR, str(_EXAMPLE_MANIFEST))
        _architects[session] = Architect.from_manifest(manifest)
    return _architects[session]


server = FastMCP(
    "iacs",
    instructions=(
        f"Call `load_manifest` with the manifest directory path to load a registry "
        "before using any other tools. "
        f"Optionally set the {_MANIFEST_ENV_VAR} environment variable so a default "
        "manifest path is available, but always call `load_manifest` explicitly."
    ),
)


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
        (_IACS_MANIFEST_DIR / "format_guide.yaml").read_text(encoding="utf-8")
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
        """Recursively collect component specs from a nested component mapping.

        Leaf components (list values) are extracted directly. Parent components
        (dict values with a "data" key) have their own spec extracted from
        "data", then their children are visited recursively. The "data" key
        itself is skipped as a component name since it holds the parent's own
        component list, not a child component.

        Results are appended to the outer ``comp_sections`` list.
        """
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
            from iacs.architect import Architect
            arch = Architect.from_manifest(tmp_dir)
        except Exception:
            return f"Validation error:\n{traceback.format_exc()}"

    types = arch.registry.component_types
    return f"Valid. Component types found: {types}"


# ---------------------------------------------------------------------------
# Audit component helpers
# ---------------------------------------------------------------------------

def _available_audit_components() -> dict[str, str]:
    """Return a mapping of audit component type name to its run_dataflow argument.

    Reads the iacs_component.audit section of components.yaml and derives the
    dataflow name as "audit.<component_type>" for each child (excluding "data").
    """
    comp_data = yaml.safe_load(
        (_BUILTINS_DIR / "components.yaml").read_text(encoding="utf-8")
    )
    audit_section = comp_data.get("iacs_component", {}).get("audit", {})
    return {
        key: f"audit.{key}"
        for key in audit_section
        if key != "data"
    }


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@server.tool()
def load_manifest(manifest_path: str, ctx: Context) -> str:
    """Load an iacs manifest from a directory path, replacing the current registry.

    Args:
        manifest_path: Path to the manifest directory.
    """
    from iacs.architect import Architect
    arch = Architect.from_manifest(manifest_path)
    _architects[ctx.request_context.session] = arch
    return f"Loaded manifest from {manifest_path!r}. Component types: {arch.registry.component_types}"


@server.tool()
def list_component_types(ctx: Context) -> str:
    """List all component types in the registry, plus audit components that can be generated.

    Loaded component types are immediately queryable with view_component or
    view_entity. Audit components listed as "available" are not yet in the
    registry and must first be generated with run_dataflow.
    """
    loaded = _get_architect(ctx).registry.component_types
    audit_map = _available_audit_components()
    unloaded = {ct: df for ct, df in audit_map.items() if ct not in loaded}

    lines = [f"Loaded component types: {loaded}"]
    if unloaded:
        lines.append("\nAvailable audit components (not yet generated):")
        for comp_type, dataflow in unloaded.items():
            lines.append(f"  - {comp_type}: run run_dataflow('{dataflow}') to generate")
    return "\n".join(lines)


@server.tool()
def view_component(component_type: str, ctx: Context, format: str = "csv") -> str:
    """Return all data for a component type.

    Args:
        component_type: The name of the component type to view.
        format: Output format — "csv" (default) or "markdown" for a
            human-readable table.
    """
    arch = _get_architect(ctx)
    df = arch.registry.view_df(component_type).reset_index()
    if format == "markdown":
        return df.to_markdown(index=False)
    return df.to_csv(index=False)


@server.tool()
def view_entity(entity_id: str, ctx: Context, format: str = "markdown") -> str:
    """Return all component data for a specific entity across every component type.

    Args:
        entity_id: Entity hash or human-readable alias (e.g. "feed_cats" or
            "feeding_system.feed_cats").
        format: Output format — "markdown" (default) or "csv".
    """
    arch = _get_architect(ctx)
    components = arch.registry.view_entity_df(entity_id)
    if not components:
        return f"No data found for entity {entity_id!r}."
    sections = []
    for comp_type, df in components.items():
        if format == "markdown":
            sections.append(f"### {comp_type}\n\n{df.to_markdown()}")
        else:
            sections.append(f"# {comp_type}\n\n{df.to_csv()}")
    return "\n\n".join(sections)


@server.tool()
def run_dataflow(name: str, ctx: Context) -> str:
    """Load and execute a dataflow, storing any new components in the registry.

    Use this to generate optional components such as audit results.
    Available dataflows: "audit.requirement_coverage", "audit.traceability",
    "audit.todo".

    Args:
        name: Dotted module path relative to iacs.dataflows
            (e.g. "audit.requirement_coverage").
    """
    arch = _get_architect(ctx)
    before = set(arch.registry.component_types)
    arch.execute(name)
    after = set(arch.registry.component_types)
    added = sorted(after - before)
    if added:
        return f"Dataflow {name!r} complete. New component types: {added}"
    return f"Dataflow {name!r} complete. No new component types added."


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
