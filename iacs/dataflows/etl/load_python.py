"""Hamilton DAG for loading entity-first data from Python source files."""

import ast
from pathlib import Path


def _module_qualified_name(file_id: str) -> str:
    """Derive a dotted module name from a file identifier."""
    parts = list(Path(file_id).with_suffix("").parts)
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


def raw_python_strings(input_dirs: list[str], python_strings: dict[str, str] = None) -> dict[str, str]:
    """Read Python source file contents as raw text, combined with directly-provided strings.

    Parameters
    ----------
    input_dirs : list[str]
        A list of Python file paths or directory paths. Directories are
        searched recursively for .py files.
    python_strings : dict[str, str], optional
        A dict keyed by identifier of raw Python source text to merge in
        directly, without reading from disk. Keys read from ``input_dirs``
        take precedence over identical keys in ``python_strings``.

    Returns
    -------
    dict[str, str]
        A dict keyed by file identifier, where each value is the raw Python
        source text for that file.
    """
    cwd = Path.cwd()
    all_files: list[tuple[Path, str]] = []

    for item in input_dirs:
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

    result = dict(python_strings) if python_strings else {}
    for file_path, file_id in all_files:
        try:
            result[file_id] = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
    return result


def raw_entity_first_data(raw_python_strings: dict[str, str]) -> dict:
    """Parse raw Python source text into entity-first dicts, keyed by file identifier.

    Parses every source string and extracts entities from modules, classes,
    and functions that have a docstring or ``__iacs__`` metadata. Entity keys
    are fully-qualified dotted names derived from the file identifier (e.g.
    ``iacs.dataflows.etl.load_manifest.raw_entity_first_data``).

    Parameters
    ----------
    raw_python_strings : dict[str, str]
        A dict keyed by file identifier, where each value is raw Python
        source text.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the entity-first
        dict of entities extracted from that source.
    """
    result = {}
    for file_id, source in raw_python_strings.items():
        try:
            tree = ast.parse(source, filename=file_id)
        except SyntaxError:
            continue
        module_name = _module_qualified_name(file_id)
        entities = _extract_entities(tree, module_name)
        if entities:
            result[file_id] = entities

    return result
