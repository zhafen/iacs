#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo '{"async": true, "asyncTimeout": 120000}'

# Install iacs with MCP extras so uvx can run it offline
uvx --from "iacs[mcp]" iacs-mcp --help > /dev/null 2>&1 || true

# Register the MCP server in user config if not already present
python3 - <<'PYEOF'
import json, os

claude_json = os.path.expanduser("~/.claude.json")
with open(claude_json) as f:
    config = json.load(f)

servers = config.setdefault("mcpServers", {})
if "iacs" not in servers:
    servers["iacs"] = {
        "type": "stdio",
        "command": "uvx",
        "args": ["--from", "iacs[mcp]", "iacs-mcp"],
        "env": {}
    }
    with open(claude_json, "w") as f:
        json.dump(config, f, indent=2)
    print("Registered iacs MCP server in ~/.claude.json")
else:
    print("iacs MCP server already registered")
PYEOF

# Install project dependencies
cd "${CLAUDE_PROJECT_DIR}"
uv sync
