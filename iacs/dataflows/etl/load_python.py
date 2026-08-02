"""Hamilton DAG for loading entity-first data from Python source files."""

import ast
import re
import textwrap
from pathlib import Path

import yaml

from ...config import DOCSTRING_COMPONENTS_PATTERN

_COMPONENTS_HEADER_RE = re.compile(DOCSTRING_COMPONENTS_PATTERN, re.MULTILINE)
_SECTION_HEADER_RE = re.compile(r"^[ \t]*\S.*\n[ \t]*-{3,}[ \t]*$", re.MULTILINE)


def _split_docstring_components(docstring: str) -> tuple[str, str | None]:
    """Split a docstring into (description_text, components_yaml_text).

    Looks for a numpy-style "Components" section (see
    ``iacs.config.DOCSTRING_COMPONENTS_PATTERN``) and pulls its body out
    separately from the rest of the docstring, which becomes the
    description text. Returns ``(docstring, None)`` unchanged if no
    Components section is present.
    """
    match = _COMPONENTS_HEADER_RE.search(docstring)
    if match is None:
        return docstring, None

    before = docstring[: match.start()].rstrip()
    rest = docstring[match.end():]
    next_header = _SECTION_HEADER_RE.search(rest)
    if next_header:
        section_text = rest[: next_header.start()]
        after = rest[next_header.start():].lstrip("\n")
    else:
        section_text = rest
        after = ""

    description = "\n\n".join(part for part in (before, after) if part)
    components_yaml = textwrap.dedent(section_text).strip()
    return description, (components_yaml or None)


def _parse_components_yaml(text: str) -> list:
    """Parse a docstring Components section into a list of component entries.

    Returns an empty list if the text fails to parse as YAML or doesn't
    parse to a list (the expected shape for a component list).
    """
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(parsed, list):
        return []
    return parsed


def _find_iacs_meta(stmts: list) -> dict | None:
    """Return the value of the first __iacs__ = {...} assignment in stmts, or None."""
    for stmt in stmts[:5]:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__iacs__"
            and isinstance(stmt.value, ast.Dict)
        ):
            try:
                return ast.literal_eval(stmt.value)
            except (ValueError, TypeError):
                pass
    return None


def _make_components(docstring: str | None, iacs_meta: dict | None) -> list | None:
    """Build a component list from a docstring and __iacs__ metadata, or None if empty.

    A docstring's "Components" section (see ``_split_docstring_components``)
    is parsed as YAML and merged into the component list rather than the
    description; it is not included in either part of a round trip: it
    is excluded from the description text, and also excluded from manifest
    export (see ``iacs.dataflows.etl.export_manifest``), since it lives in
    a Python source file rather than a standalone YAML file.
    """
    description, components_yaml = (
        _split_docstring_components(docstring) if docstring else (None, None)
    )
    components = []
    if description:
        components.append({"description": description.strip()})
    if iacs_meta:
        for key, value in iacs_meta.items():
            components.append({key: value})
    if components_yaml:
        components.extend(_parse_components_yaml(components_yaml))
    if not components:
        return None
    return components


def _extract_entities(tree: ast.Module, module_name: str) -> dict:
    """Walk an AST module and return a flat entity-first dict.

    Entity keys are fully-qualified dotted names within the module
    (e.g. ``iacs.dataflows.etl.load_manifest.MyClass.my_method``).
    Only constructs with a docstring or ``__iacs__`` assignment are included.
    """
    entities: dict = {}

    components = _make_components(ast.get_docstring(tree), _find_iacs_meta(tree.body))
    if components is not None:
        entities[module_name] = components

    def _walk(stmts: list, prefix: str) -> None:
        for node in stmts:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}.{node.name}"
                comps = _make_components(ast.get_docstring(node), _find_iacs_meta(node.body))
                if comps is not None:
                    entities[qual] = comps
                _walk(node.body, qual)
            elif isinstance(node, ast.ClassDef):
                qual = f"{prefix}.{node.name}"
                comps = _make_components(ast.get_docstring(node), _find_iacs_meta(node.body))
                if comps is not None:
                    entities[qual] = comps
                _walk(node.body, qual)

    _walk(tree.body, module_name)
    return entities


def parsed_asts(raw_python_strings: dict[str, str]) -> dict[str, ast.Module]:
    """Parse raw Python source text into AST modules, keyed by file identifier.

    Files that fail to parse (e.g. non-Python content, syntax errors) are
    silently dropped.

    Parameters
    ----------
    raw_python_strings : dict[str, str]
        A dict keyed by file identifier, where each value is raw Python
        source text.

    Returns
    -------
    dict[str, ast.Module]
        A dict keyed by file identifier, where each value is the parsed AST
        module for that file's source.
    """
    result = {}
    for file_id, source in raw_python_strings.items():
        try:
            result[file_id] = ast.parse(source, filename=file_id)
        except SyntaxError:
            continue
    return result


def module_names(parsed_asts: dict[str, ast.Module]) -> dict[str, str]:
    """Derive a dotted module name for each successfully parsed file.

    e.g. ``"iacs/dataflows/etl/load_python.py"`` becomes
    ``"iacs.dataflows.etl.load_python"``.
    """
    return {
        file_id: ".".join(Path(file_id).with_suffix("").parts)
        for file_id in parsed_asts
    }


def raw_entity_first_data(
    parsed_asts: dict[str, ast.Module],
    module_names: dict[str, str],
) -> dict:
    """Extract entity-first dicts from parsed ASTs, keyed by file identifier.

    Extracts entities from modules, classes, and functions that have a
    docstring or ``__iacs__`` metadata. Entity keys are fully-qualified
    dotted names derived from the file identifier (e.g.
    ``iacs.dataflows.etl.load_manifest.raw_entity_first_data``).

    Parameters
    ----------
    parsed_asts : dict[str, ast.Module]
        A dict keyed by file identifier, where each value is the parsed AST
        module for that file's source, as returned by ``parsed_asts``.
    module_names : dict[str, str]
        A dict keyed by file identifier, where each value is that file's
        dotted module name, as returned by ``module_names``.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the entity-first
        dict of entities extracted from that source.
    """
    result = {}
    for file_id, tree in parsed_asts.items():
        entities = _extract_entities(tree, module_names[file_id])
        if entities:
            result[file_id] = entities
    return result


FINAL_VAR = "raw_entity_first_data"
