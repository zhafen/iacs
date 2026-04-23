"""MCP server exposing iacs registry tools."""

import os

from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

server = FastMCP("iacs")

_architect: Architect | None = None


def _get_architect() -> Architect:
    global _architect
    if _architect is None:
        manifest = os.environ.get("IACS_MANIFEST")
        if not manifest:
            raise RuntimeError(
                "IACS_MANIFEST environment variable is not set. "
                "Set it to the path of your manifest directory."
            )
        _architect = Architect.from_manifest(manifest)
    return _architect


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
