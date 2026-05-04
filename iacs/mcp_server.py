"""Bare-bones stdio MCP server for incremental debugging."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from iacs.architect import Architect

_MANIFEST_ENV_VAR = "IACS_MANIFEST"
_EXAMPLE_MANIFEST = Path(__file__).parent.parent / "examples" / "example"


@asynccontextmanager
async def _lifespan(mcp_server):
    manifest = os.environ.get(_MANIFEST_ENV_VAR, str(_EXAMPLE_MANIFEST))
    arch = Architect.from_manifest(manifest)
    print(f"Loaded manifest: {manifest}", file=sys.stderr)
    print(f"Component types: {arch.registry.component_types}", file=sys.stderr)
    yield


server = FastMCP("iacs", lifespan=_lifespan)


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
