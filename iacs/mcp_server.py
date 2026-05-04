"""Bare-bones stdio MCP server for incremental debugging."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

_MANIFEST_ENV_VAR = "IACS_MANIFEST"
_EXAMPLE_MANIFEST = Path(__file__).parent.parent / "examples" / "example"

_manifest_path: str = ""
_architect: Architect | None = None


def _get_architect() -> Architect:
    global _architect
    if _architect is None:
        _architect = Architect.from_manifest(_manifest_path)
    return _architect


server = FastMCP("iacs")


@server.tool()
def ping() -> str:
    """Return a simple confirmation that the MCP server is running."""
    return "pong"


@server.tool()
def list_component_types() -> list[str]:
    """List all component types in the loaded manifest."""
    return _get_architect().registry.component_types


def main() -> None:
    global _manifest_path
    _manifest_path = os.environ.get(_MANIFEST_ENV_VAR, str(_EXAMPLE_MANIFEST))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
