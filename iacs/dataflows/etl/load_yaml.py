"""Hamilton DAG for loading entity-first data from EC files."""

from pathlib import Path

import yaml


_BUILTINS_DIR = Path(__file__).parent.parent.parent / "builtins"


def raw_yaml_strings(input_dirs: list[str], yaml_strings: dict[str, str] = None) -> dict[str, str]:
    """Read EC file contents as raw text, combined with directly-provided YAML strings.

    Always includes all EC files from the builtins directory, each identified
    as "builtins.<stem>". User-provided files are identified by their path
    relative to the current working directory.

    Parameters
    ----------
    input_dirs : list[str]
        A list of EC file paths or directory paths. Directories are searched
        recursively for EC files.
    yaml_strings : dict[str, str], optional
        A dict keyed by identifier of raw YAML text to merge in directly,
        without reading from disk. Keys read from ``input_dirs`` take
        precedence over identical keys in ``yaml_strings``.

    Returns
    -------
    dict[str, str]
        A dict keyed by file identifier, where each value is the raw YAML
        text for that file.
    """
    cwd = Path.cwd()
    all_files: list[tuple[Path, str]] = []

    for item in input_dirs:
        p = Path(item)
        if p.is_file() and p.suffix in (".yaml", ".yml"):
            try:
                file_id = str(p.relative_to(cwd))
            except ValueError:
                file_id = str(p)
            all_files.append((p, file_id))
        elif p.is_dir():
            for f in sorted(p.rglob("*.y*ml")):
                if f.suffix in (".yaml", ".yml"):
                    try:
                        file_id = str(f.relative_to(cwd))
                    except ValueError:
                        file_id = str(f)
                    all_files.append((f, file_id))

    for f in sorted(_BUILTINS_DIR.rglob("*.y*ml")):
        if f.suffix in (".yaml", ".yml"):
            builtin_id = f"builtins.{f.stem}"
            all_files.append((f, builtin_id))

    result = dict(yaml_strings) if yaml_strings else {}
    for file_path, file_id in all_files:
        result[file_id] = file_path.read_text(encoding="utf-8")
    return result


def raw_entity_first_data(raw_yaml_strings: dict[str, str]) -> dict:
    """Parse raw YAML text into entity-first dicts, keyed by file identifier.

    Parameters
    ----------
    raw_yaml_strings : dict[str, str]
        A dict keyed by file identifier, where each value is raw YAML text.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the dict of
        entities loaded from that file's YAML text.
    """
    result = {}
    for file_id, content in raw_yaml_strings.items():
        result[file_id] = yaml.safe_load(content) or {}
    return result
