"""MCP server exposing iacs registry tools."""

import os
import tempfile
import traceback
from pathlib import Path

import yaml
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
def view_component(component_type: str, format: str = "csv") -> str:
    """Return all data for a component type.

    Args:
        component_type: The name of the component type to view.
        format: Output format — "csv" (default) or "markdown" for a
            human-readable table.
    """
    arch = _get_architect()
    df = arch.registry.view_df(component_type).reset_index()
    if format == "markdown":
        return df.to_markdown(index=False)
    return df.to_csv(index=False)


_FORMAT_DESCRIPTION = """\
# Entity-First YAML Format

Entities are top-level keys. Each entity's value is either:
- A **list** (flat entity): each list item is a component.
- A **dict** (nested entity): sub-entities are dict keys; own components live
  under the special `data` key (also a list).

## Components (list items)

| Form | Meaning |
|------|---------|
| `- tag_name` | Bare-string tag — no value |
| `- key: value` | Scalar component |
| `- key:` | Structured component with sub-fields |
|   `    subfield: value` | |

## Built-in component types

- `description: <str>` — human-readable description
- `requirement:` — marks an entity as a requirement
    - `priority: <float 0-1>` (optional)
    - `value: functional | non_functional` (optional)
- `solution of: <entity_path>` — this entity solves the referenced requirement
- `parent: <entity_key>` — explicit parent for type hierarchy
- `alias: <str>` — alternate identifier
- `effort:` — work estimate
    - `value: <number>`
    - `schedule: <str>` (optional, e.g. "weekly")
- `status: <str>` — e.g. "in progress", "done"
- `system` — bare tag marking an entity as a system
- `todo: <str>` — outstanding action item
- `field:` — declares a typed data field
    - `value: <field_name>`
    - `type: str | int | float | bool`
    - `description: <str>` (optional)
    - `nullable: true | false` (optional)
    - `unique: true | false` (optional)

## Canonical example

```yaml
make_cats_happy:
    data:
        - description: The mission of our cat-happiness device.
        - requirement:
              priority: 1
    feed_cats:
        - requirement:
              priority: 0.9
        - alias: feed_cats

cat_happiness_device:
    data:
        - description: An all-in-one tool to make cats happy.
        - solution of: make_cats_happy
        - system
    feeding_system:
        - description: The task to feed the cats.
        - solution of: make_cats_happy.feed_cats
        - effort:
              value: 8
        - status: in progress
```

## Rules

1. Entity keys use `snake_case`. Nested paths use dots: `parent.child`.
2. A flat entity (list value) cannot have sub-entities.
3. `solution of` values are dot-separated entity paths (relative or absolute).
4. Multiple components of the same type on one entity are allowed (e.g. two
   `effort` entries for different schedules).
5. Indentation is significant — use consistent spaces (2 or 4).
"""


def _validate_yaml_string(yaml_string: str) -> str:
    """Parse and validate entity-first YAML, returning a result message.

    Writes the YAML to a temporary file and runs it through the full
    Architect pipeline. Returns a success message listing component types
    found, or an error message describing what went wrong.
    """
    try:
        yaml.safe_load(yaml_string)
    except yaml.YAMLError as exc:
        return f"YAML syntax error:\n{exc}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        yaml_file = Path(tmp_dir) / "input.yaml"
        yaml_file.write_text(yaml_string, encoding="utf-8")
        try:
            arch = Architect.from_manifest(tmp_dir)
        except Exception:
            return f"Validation error:\n{traceback.format_exc()}"

    types = arch.registry.component_types
    return f"Valid. Component types found: {types}"


@server.tool()
def describe_format() -> str:
    """Return the entity-first YAML format specification with a canonical example.

    Use this before transcribing text into iacs YAML to understand the
    required structure, built-in component types, and formatting rules.
    """
    return _FORMAT_DESCRIPTION


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
