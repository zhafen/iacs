#!/usr/bin/env bash
set -euo pipefail

# Install iacs from the local repo into .venv
uv sync
uv pip install -e ".[mcp]"
