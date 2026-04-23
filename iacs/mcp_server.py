"""MCP server exposing iacs registry tools."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

server = FastMCP("iacs")

_BUILTIN_MANIFEST = Path(__file__).parent.parent / "examples" / "example"

_architect: Architect | None = None


def _get_architect() -> Architect:
    global _architect
    if _architect is None:
        manifest = os.environ.get("IACS_MANIFEST", str(_BUILTIN_MANIFEST))
        _architect = Architect.from_manifest(manifest)
    return _architect


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
def view_component(component_type: str) -> str:
    """Return all data for a component type as CSV.

    Args:
        component_type: The name of the component type to view.
    """
    arch = _get_architect()
    df = arch.registry.view_df(component_type).reset_index()
    return df.to_csv(index=False)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
