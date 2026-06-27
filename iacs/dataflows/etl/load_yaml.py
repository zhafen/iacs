"""Hamilton DAG for loading entity-first data from EC files."""

from pathlib import Path

import yaml


_BUILTINS_DIR = Path(__file__).parent.parent.parent / "builtins"


def raw_entity_first_data(input_dir: list[str]) -> dict:
    """Load EC files from a list of files or directories.

    Always includes all EC files from the builtins directory, each identified
    as "builtins.<stem>". User-provided files are identified by their path
    relative to the current working directory.

    Parameters
    ----------
    input_dir : list[str]
        A list of EC file paths or directory paths. Directories are searched
        recursively for EC files.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the dict of
        entities loaded from that file.
    """
    cwd = Path.cwd()
    all_files: list[tuple[Path, str]] = []

    for item in input_dir:
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

    result = {}
    for file_path, file_id in all_files:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        result[file_id] = data
    return result
