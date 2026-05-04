"""Bare-bones stdio MCP server for incremental debugging."""

from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

server = FastMCP("iacs")


@server.tool()
def ping() -> str:
    """Return a simple confirmation that the MCP server is running."""
    return "pong"


@server.tool()
def list_component_types(manifest_path: str) -> list[str]:
    """Load a manifest and return its component types.

    Args:
        manifest_path: Path to the manifest directory.
    """
    arch = Architect.from_manifest(manifest_path)
    return arch.registry.component_types


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
