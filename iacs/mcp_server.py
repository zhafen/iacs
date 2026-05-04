"""Bare-bones stdio MCP server for incremental debugging."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("iacs")


@server.tool()
def ping() -> str:
    """Return a simple confirmation that the MCP server is running."""
    return "pong"


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
