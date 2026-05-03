# MCP Server

iacs ships an [MCP](https://modelcontextprotocol.io) server that exposes the registry tools to AI assistants such as Claude.

## Quickstart

Add the following to your `.mcp.json` (or Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "iacs": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "iacs[mcp]", "iacs-mcp"],
      "env": {
        "IACS_MANIFEST": "/path/to/your/manifest"
      }
    }
  }
}
```

Replace `/path/to/your/manifest` with the directory that contains your YAML manifest files. If you omit `IACS_MANIFEST`, the server loads the built-in example manifest.

## Configuration

| Environment variable | Description |
|---|---|
| `IACS_MANIFEST` | Path to the manifest directory to load on startup. If unset, the built-in example manifest is used. |

To confirm which manifest is active, call the `get_manifest_path` tool from your AI assistant.

## Available Tools

| Tool | Description |
|---|---|
| `get_manifest_path` | Show the currently loaded manifest path and configuration source. |
| `load_manifest` | Load a manifest from a directory path, replacing the current registry. |
| `list_component_types` | List all component types in the registry. |
| `view_component` | View all data for a component type (CSV or Markdown). |
| `describe_format` | Return the entity-first YAML format spec and canonical example. |
| `validate_yaml` | Validate entity-first YAML and report errors. |
