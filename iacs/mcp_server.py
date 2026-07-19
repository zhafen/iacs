"""MCP server exposing iacs registry tools."""
from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

from iacs.commands import (
    MANIFEST_ENV_VAR as _MANIFEST_ENV_VAR,
    EXAMPLE_MANIFEST as _EXAMPLE_MANIFEST,
    BUILTINS_DIR as _BUILTINS_DIR,
    IACS_MANIFEST_DIR as _IACS_MANIFEST_DIR,
    available_audit_components as _available_audit_components,
    build_format_description as _build_format_description,
    cmd_list_component_types,
    cmd_refresh,
    cmd_run_dataflow,
    cmd_view_component,
    cmd_view_entity,
    get_manifest_path_str,
    make_registrar,
    parse_manifest_env as _parse_manifest_env,
    validate_yaml_string as _validate_yaml_string,
)

if TYPE_CHECKING:
    from iacs.registrar import Registrar

_registrars: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _get_registrar(ctx: Context) -> "Registrar":
    session = ctx.request_context.session
    if session not in _registrars:
        _registrars[session] = make_registrar(_parse_manifest_env())
    return _registrars[session]


server = FastMCP(
    "iacs",
    instructions=(
        f"Call `load_manifest` with one or more manifest directory paths to load a "
        "registry before using any other tools. "
        f"Optionally set {_MANIFEST_ENV_VAR} (colon-separated on Unix) so a default "
        "set of manifest paths is available on startup. "
        "Call `get_manifest_path` to confirm which paths are currently configured."
    ),
)


@server.tool()
def get_manifest_path() -> str:
    """Return the path(s) of the currently loaded manifest.

    Also shows the environment variable name used to configure a default
    manifest path at startup.
    """
    return get_manifest_path_str()


@server.tool()
def load_manifest(manifest_paths: list[str], ctx: Context) -> str:
    """Load an iacs manifest from a directory path, replacing the current registry.

    Args:
        manifest_paths: List of paths to manifest directories.
    """
    reg = make_registrar(manifest_paths)
    _registrars[ctx.request_context.session] = reg
    paths_str = ", ".join(repr(p) for p in manifest_paths)
    return f"Loaded manifest from {paths_str}. Component types: {reg.registry.component_types}"


@server.tool()
def list_component_types(ctx: Context) -> str:
    """List all component types in the registry, plus audit components that can be generated.

    Loaded component types are immediately queryable with view_component or
    view_entity. Audit components listed as "available" are not yet in the
    registry and must first be generated with run_dataflow.
    """
    return cmd_list_component_types(_get_registrar(ctx))


@server.tool()
def view_component(component_type: str, ctx: Context, format: str = "csv") -> str:
    """Return all data for a component type.

    Args:
        component_type: The name of the component type to view.
        format: Output format — "csv" (default) or "markdown" for a
            human-readable table.
    """
    return cmd_view_component(_get_registrar(ctx), component_type, format)


@server.tool()
def view_entity(entity_id: str, ctx: Context, format: str = "markdown") -> str:
    """Return all component data for a specific entity across every component type.

    Args:
        entity_id: Entity hash or human-readable alias (e.g. "feed_cats" or
            "feeding_system.feed_cats").
        format: Output format — "markdown" (default) or "csv".
    """
    return cmd_view_entity(_get_registrar(ctx), entity_id, format)


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
    return cmd_run_dataflow(_get_registrar(ctx), name)


@server.tool()
def refresh(ctx: Context) -> str:
    """Run the ETL export and write normalised EC files back to the original source paths.

    Executes the full export pipeline against the currently loaded registry
    (which has already passed through load → validate → derive) and saves
    each EC file back to its original location, normalising formatting and
    resolving any derived fields in-place.

    Returns a summary listing each file that was written.
    """
    return cmd_refresh(_get_registrar(ctx))


@server.tool()
def describe_format() -> str:
    """Return the entity-first YAML format specification with a canonical example.

    Use this before transcribing text into an EC file to understand the
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
