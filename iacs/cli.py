"""Command-line interface for iacs."""
from __future__ import annotations

import argparse
import sys

from iacs.commands import (
    MANIFEST_ENV_VAR,
    available_audit_components,
    build_format_description,
    cmd_list_component_types,
    cmd_view_component,
    cmd_view_entity,
    get_manifest_path_str,
    make_architect,
    parse_manifest_env,
    validate_yaml_string,
)


def _resolve_manifest_paths(args: argparse.Namespace) -> list[str]:
    return args.manifest if args.manifest else parse_manifest_env()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iacs",
        description="Infrastructure-as-Code Sketch CLI",
    )
    parser.add_argument(
        "--manifest",
        metavar="PATH",
        action="append",
        help=(
            f"Manifest directory path. May be repeated for multiple directories. "
            f"Defaults to ${MANIFEST_ENV_VAR} or the built-in example."
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser(
        "manifest",
        help="Show the manifest path(s) that would be loaded.",
    )

    sub.add_parser(
        "list-types",
        help="List all component types in the registry.",
    )

    p_vc = sub.add_parser(
        "view-component",
        help="View all data for a component type.",
    )
    p_vc.add_argument("component_type", help="Component type name.")
    p_vc.add_argument(
        "--format",
        choices=["csv", "markdown"],
        default="csv",
        help="Output format (default: csv).",
    )

    p_ve = sub.add_parser(
        "view-entity",
        help="View all components for a specific entity.",
    )
    p_ve.add_argument(
        "entity_id",
        help="Entity hash or alias (e.g. 'feed_cats' or 'system.feed_cats').",
    )
    p_ve.add_argument(
        "--format",
        choices=["csv", "markdown"],
        default="markdown",
        help="Output format (default: markdown).",
    )

    p_rd = sub.add_parser(
        "run-dataflow",
        help=(
            "Execute a dataflow and show any newly generated component tables. "
            "Available dataflows: audit.requirement_coverage, audit.traceability, audit.todo."
        ),
    )
    p_rd.add_argument(
        "name",
        help="Dotted dataflow name relative to iacs.dataflows (e.g. 'audit.requirement_coverage').",
    )
    p_rd.add_argument(
        "--format",
        choices=["csv", "markdown"],
        default="markdown",
        help="Output format for newly generated component tables (default: markdown).",
    )

    sub.add_parser(
        "describe-format",
        help="Show the entity-first YAML format specification.",
    )

    p_vy = sub.add_parser(
        "validate-yaml",
        help="Validate entity-first YAML and report any errors.",
    )
    p_vy.add_argument(
        "file",
        nargs="?",
        help="Path to a YAML file. Reads from stdin if omitted.",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "manifest":
        print(get_manifest_path_str(args.manifest))
        return

    if args.command == "describe-format":
        print(build_format_description())
        return

    if args.command == "validate-yaml":
        if args.file:
            from pathlib import Path
            yaml_string = Path(args.file).read_text(encoding="utf-8")
        else:
            yaml_string = sys.stdin.read()
        result = validate_yaml_string(yaml_string)
        print(result)
        if not result.startswith("Valid."):
            sys.exit(1)
        return

    manifest_paths = _resolve_manifest_paths(args)
    arch = make_architect(manifest_paths)

    if args.command == "list-types":
        print(cmd_list_component_types(arch))

    elif args.command == "view-component":
        print(cmd_view_component(arch, args.component_type, args.format))

    elif args.command == "view-entity":
        print(cmd_view_entity(arch, args.entity_id, args.format))

    elif args.command == "run-dataflow":
        before = set(arch.registry.component_types)
        arch.execute(args.name)
        after = set(arch.registry.component_types)
        added = sorted(after - before)
        if added:
            print(f"Dataflow {args.name!r} complete. New component types: {added}\n")
            for comp_type in added:
                print(f"=== {comp_type} ===")
                print(cmd_view_component(arch, comp_type, args.format))
        else:
            print(f"Dataflow {args.name!r} complete. No new component types added.")


if __name__ == "__main__":
    main()
