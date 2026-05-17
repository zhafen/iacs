"""Hamilton DAG for loading entity-first data from Python source files."""

import ast
from pathlib import Path


def _module_qualified_name(file_path: Path, cwd: Path) -> str:
    """Derive a dotted module name from a file path relative to cwd."""
    try:
        rel = file_path.relative_to(cwd)
    except ValueError:
        rel = file_path
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


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
    """Build a component list from a docstring and __iacs__ metadata, or None if empty."""
    if not docstring and not iacs_meta:
        return None
    components = []
    if docstring:
        components.append({"description": docstring.strip()})
    if iacs_meta:
        for key, value in iacs_meta.items():
            components.append({key: value})
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


def raw_entity_first_data(input_dir: list[str]) -> dict:
    """Load Python source files from a list of files or directories.

    Parses every ``.py`` file found and extracts entities from modules,
    classes, and functions that have a docstring or ``__iacs__`` metadata.
    Entity keys are fully-qualified dotted names derived from the file path
    (e.g. ``iacs.dataflows.etl.load_manifest.raw_entity_first_data``).

    Parameters
    ----------
    input_dir : list[str]
        A list of Python file paths or directory paths. Directories are
        searched recursively for .py files.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the entity-first
        dict of entities extracted from that file.
    """
    cwd = Path.cwd()
    all_files: list[tuple[Path, str]] = []

    for item in input_dir:
        p = Path(item)
        if p.is_file() and p.suffix == ".py":
            try:
                file_id = str(p.relative_to(cwd))
            except ValueError:
                file_id = str(p)
            all_files.append((p, file_id))
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                try:
                    file_id = str(f.relative_to(cwd))
                except ValueError:
                    file_id = str(f)
                all_files.append((f, file_id))

    result = {}
    for file_path, file_id in all_files:
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError):
            continue
        module_name = _module_qualified_name(file_path, cwd)
        entities = _extract_entities(tree, module_name)
        if entities:
            result[file_id] = entities

    return result
