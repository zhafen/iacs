"""Hamilton DAG for converting entity-centered data to component-centered data."""

import re
from pathlib import Path

import ibis
import ibis.expr.types as ir
import pandas as pd
import yaml

from ..registry import Registry
from ..utils import dhash


_BUILTIN_COMPONENTS = Path(__file__).parent.parent.parent / "builtins" / "components.yaml"
_BUILTIN_ID = "builtins.components"


def raw_csv_data(input_dir: list[str]) -> dict[str, pd.DataFrame]:
    """Load CSV files from a list of files or directories (user-provided only, not builtins).

    The filename stem (without extension) of each CSV file becomes the component
    type for all rows in that file. Only directories and explicit CSV file paths
    from ``input_dir`` are searched — the builtins directory is never included.

    Parameters
    ----------
    input_dir : list[str]
        A list of CSV file paths or directory paths. Directories are searched
        recursively for CSV files.

    Returns
    -------
    dict[str, pd.DataFrame]
        A dict keyed by the file path identifier (relative to cwd when possible),
        where each value is a DataFrame of that CSV's rows.
    """
    cwd = Path.cwd()
    all_files: list[tuple[Path, str]] = []

    for item in input_dir:
        p = Path(item)
        if p.is_file() and p.suffix == ".csv":
            try:
                file_id = str(p.relative_to(cwd))
            except ValueError:
                file_id = str(p)
            all_files.append((p, file_id))
        elif p.is_dir():
            for f in sorted(p.rglob("*.csv")):
                try:
                    file_id = str(f.relative_to(cwd))
                except ValueError:
                    file_id = str(f)
                all_files.append((f, file_id))

    result = {}
    for file_path, file_id in all_files:
        result[file_id] = pd.read_csv(file_path)
    return result


def csv_component_tables(raw_csv_data: dict[str, pd.DataFrame]) -> dict[str, ir.Table]:
    """Convert raw CSV data into component tables, one table per component type.

    The stem of each CSV filename is the component type for every row in that
    file. Each row receives a unique entity_id computed as
    ``dhash(file_path_id + ":" + str(row_index))``, a fixed ``component_index``
    of 0, a NULL ``modifier``, and one column per CSV column (the CSV column
    names become field names, analogous to sub-field components in YAML).

    When multiple CSV files share the same stem (component type) their rows are
    unioned into a single table.

    Parameters
    ----------
    raw_csv_data : dict[str, pd.DataFrame]
        Mapping of file path identifier → DataFrame as returned by
        ``raw_csv_data``.

    Returns
    -------
    dict[str, ir.Table]
        Keys are component types (CSV filename stems); each value is an ibis
        Table with columns: entity_id, component_index, modifier, and one
        column per CSV field.
    """
    # Accumulate DataFrames per component type (stem).
    per_stem: dict[str, list[pd.DataFrame]] = {}
    for file_id, df in raw_csv_data.items():
        stem = Path(file_id).stem
        rows = []
        for i, row in df.iterrows():
            entity_id = dhash(file_id + ":" + str(i))
            record = {
                "entity_id": entity_id,
                "component_index": 0,
                "modifier": pd.NA,
            }
            for col in df.columns:
                record[col] = row[col]
            rows.append(record)
        part_df = pd.DataFrame(rows)
        part_df["modifier"] = part_df["modifier"].astype(pd.StringDtype())
        part_df["component_index"] = part_df["component_index"].astype("int32")
        per_stem.setdefault(stem, []).append(part_df)

    result = {}
    for stem, dfs in per_stem.items():
        combined = pd.concat(dfs, ignore_index=True)
        combined["modifier"] = combined["modifier"].astype(pd.StringDtype())
        result[stem] = ibis.memtable(combined)
    return result


def csv_spine(raw_csv_data: dict[str, pd.DataFrame]) -> ir.Table:
    """Build spine rows for entities sourced from CSV files.

    Each row in every CSV file contributes one spine row. The entity_id is
    ``dhash(file_path_id + ":" + str(row_index))``. The component_type is the
    CSV filename stem. The path follows the pattern
    ``file_path_id:stem[row_index].stem`` to remain consistent with the YAML
    spine path convention.

    Parameters
    ----------
    raw_csv_data : dict[str, pd.DataFrame]
        Mapping of file path identifier → DataFrame as returned by
        ``raw_csv_data``.

    Returns
    -------
    ir.Table
        Columns: entity_id, component_index, entity_key, component_type,
        modifier, filepath, path.  Schema matches the YAML-derived spine so the
        two can be unioned.
    """
    rows = []
    for file_id, df in raw_csv_data.items():
        stem = Path(file_id).stem
        for i in range(len(df)):
            entity_id = dhash(file_id + ":" + str(i))
            rows.append({
                "entity_id": entity_id,
                "component_index": 0,
                "entity_key": stem,
                "component_type": stem,
                "modifier": pd.NA,
                "filepath": file_id,
                "path": f"{file_id}:{stem}[{i}].{stem}",
            })
    spine_df = pd.DataFrame(rows, columns=[
        "entity_id", "component_index", "entity_key", "component_type",
        "modifier", "filepath", "path",
    ])
    for col in ("entity_id", "entity_key", "component_type", "filepath", "path"):
        spine_df[col] = spine_df[col].astype(pd.StringDtype())
    spine_df["modifier"] = spine_df["modifier"].astype(pd.StringDtype())
    spine_df["component_index"] = spine_df["component_index"].astype("int32")
    return ibis.memtable(spine_df)


def raw_entity_first_data(input_dir: list[str]) -> dict:
    """Load yaml files from a list of files or directories.

    Always includes builtins/components.yaml (identified as "builtins.components").
    User-provided files are identified by their path relative to the current
    working directory.

    Parameters
    ----------
    input_dir : list[str]
        A list of yaml file paths or directory paths. Directories are searched
        recursively for yaml files.

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

    all_files.append((_BUILTIN_COMPONENTS, _BUILTIN_ID))

    result = {}
    for file_path, file_id in all_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        result[file_id] = data
    return result


def _add_component_pairs(
    entity_path: str, index: int, component, result: list
) -> None:
    """Append (path, value) pairs for one component entry to result.

    Parameters
    ----------
    entity_path : str
        The dot-separated path to the owning entity, e.g. "a.b.c".
    index : int
        The 0-based position of this component in the entity's list
        (bare-string tags count toward the index).
    component : str | dict
        The raw YAML component value.
    result : list
        Accumulator of (path, value) string tuples.
    """
    prefix = f"{entity_path}[{index}]"
    if isinstance(component, str):
        # Tag component: bare string, no associated value.
        result.append((f"{prefix}.{component}", ""))
    elif isinstance(component, dict):
        key = next(iter(component))
        value = component[key]
        if isinstance(value, dict):
            # Component with sub-fields, e.g. {"requirement": {"priority": 1}}.
            for sub_key, sub_val in value.items():
                str_val = "" if sub_val is None else str(sub_val)
                result.append((f"{prefix}.{key}.{sub_key}", str_val))
        else:
            # Simple scalar component, e.g. {"description": "..."}.
            str_val = "" if value is None else str(value)
            result.append((f"{prefix}.{key}", str_val))


def _flatten_to_pathvalue(data: dict, parent_path: str = "") -> list[tuple[str, str]]:
    """Recursively flatten entity-first data into (path, value) string pairs.

    For flat entities (list value) the path is ``entity[N].key``.
    For nested entities (dict value with an optional ``data`` key) the entity's
    own components are at ``entity.data[N].key`` and sub-entities are processed
    recursively.
    """
    result = []
    for entity_key, entity_value in data.items():
        entity_path = f"{parent_path}.{entity_key}" if parent_path else entity_key
        if isinstance(entity_value, list):
            for i, component in enumerate(entity_value):
                _add_component_pairs(entity_path, i, component, result)
        elif isinstance(entity_value, dict):
            # Entity's own components live under the "data" key (if present).
            for i, component in enumerate(entity_value.get("data", [])):
                _add_component_pairs(f"{entity_path}.data", i, component, result)
            # Recurse into sub-entities (every key except "data").
            sub_entities = {k: v for k, v in entity_value.items() if k != "data"}
            result.extend(_flatten_to_pathvalue(sub_entities, entity_path))
    return result


def pathvalue_pairs(raw_entity_first_data: dict) -> ir.Table:
    """Convert the raw entity-first data into a database table with two fields:
    path and value, both of type str. This is the first step in the transformation
    process, and serves as a way to inspect the raw data in a tabular format before
    applying the more complex transformations.

    Each path is prefixed with the file identifier using a ':' separator, e.g.
    "examples/foo.yaml:my_entity[0].description".

    Parameters
    ----------
    raw_entity_first_data : dict
        Nested dict of the form {file_id: {entity_key: entity_data}}.

    Returns
    -------
    ir.Table
        A table with columns "path" and "value".
    """
    pairs = []
    for file_id, entities in raw_entity_first_data.items():
        for entity_path, value in _flatten_to_pathvalue(entities):
            pairs.append((f"{file_id}:{entity_path}", value))
    df = pd.DataFrame(pairs, columns=["path", "value"])
    return ibis.memtable(df)


_PATH_PATTERN = r"^(.+)\[(\d+)\]\.(.+)$"


def _with_spine_path(t: ir.Table) -> ir.Table:
    """Add a spine_path column to a table that has a 'path' column.

    Assumes all rows already match _PATH_PATTERN (pre-filter before calling).
    Also adds intermediate columns _prefix, _idx, _after, _ctf.
    """
    t = t.mutate(
        _prefix=t.path.re_extract(_PATH_PATTERN, 1),
        _idx=t.path.re_extract(_PATH_PATTERN, 2),
        _after=t.path.re_extract(_PATH_PATTERN, 3),
    )
    # _ctf: first dot-segment of _after (component_type_full, may include spaces)
    t = t.mutate(_ctf=t["_after"].re_extract(r"^([^.]*)", 1))
    return t.mutate(spine_path=t["_prefix"] + "[" + t["_idx"] + "]." + t["_ctf"])


def keyvalue_store(pathvalue_pairs: ir.Table) -> ir.Table:
    """Parse path-value pairs into a structured long-format table.

    One row per (entity, component, field). Centralises all path-parsing so
    that ``spine`` and ``component_tables`` are simple derivations.

    Returns
    -------
    ir.Table
        Columns: entity_id, entity_key, entity_path, filepath,
        component_index, component_type, modifier, spine_path, field, value.
    """
    t = pathvalue_pairs.filter(pathvalue_pairs.path.re_search(_PATH_PATTERN))
    t = _with_spine_path(t)

    # entity_path: strip the '.data' suffix that marks a nested entity's own components.
    t = t.mutate(
        entity_path=ibis.ifelse(
            t["_prefix"].endswith(".data"),
            t["_prefix"].substr(0, t["_prefix"].length() - 5),
            t["_prefix"],
        ),
        component_type=t["_ctf"].re_extract(r"^(\S+)", 1),
        modifier=t["_ctf"].re_extract(r"^\S+ (.+)$", 1).nullif(""),
        component_index=t["_idx"].cast("int32"),
    )
    # entity_id: first 12 hex chars of SHA-256 (matches dhash in utils).
    # entity_key: last segment after the last ':' or '.' in entity_path.
    # filepath: the file identifier prefix (before ':'), NULL if absent.
    t = t.mutate(
        entity_id=t.entity_path.hexdigest("sha256").substr(0, 12),
        entity_key=t.entity_path.re_extract(r"([^:.]+)$", 1),
        filepath=t.entity_path.re_extract(r"^([^:]+):", 1).nullif(""),
    )
    # field: sub-field name after the spine_path, or "value" for scalar components.
    t = t.mutate(
        field=ibis.ifelse(
            t["path"] == t["spine_path"],
            ibis.literal("value"),
            t["path"].substr(t["spine_path"].length() + 1),
        )
    )
    return t.select(
        "entity_id", "entity_key", "entity_path", "filepath",
        "component_index", "component_type", "modifier",
        "spine_path", "field", "value",
    )


def entity_id_table(keyvalue_store: ir.Table, csv_spine: ir.Table = None) -> ir.Table:
    """Build one row per entity from the key-value store and optional CSV spine.

    Returns
    -------
    ir.Table
        Columns: hash, path, value, alias, entity_key, filepath.
        ``hash`` is the entity_id; ``path`` is the full entity_path;
        ``value`` is the display ID (last two dot-segments or entity_key for
        top-level); ``alias`` is from the alias component if present.
    """
    yaml_entities = keyvalue_store.select(
        "entity_id", "entity_key", "entity_path", "filepath"
    ).distinct().to_pandas()
    yaml_entities = yaml_entities.rename(columns={"entity_id": "hash", "entity_path": "path"})

    def compute_value(row):
        entity_path = row["path"]
        entity_key = row["entity_key"]
        sep = entity_path.find(":")
        name_part = entity_path[sep + 1:] if sep != -1 else entity_path
        parts = name_part.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else entity_key

    yaml_entities["value"] = yaml_entities.apply(compute_value, axis=1)

    alias_df = (
        keyvalue_store
        .filter(
            (keyvalue_store["component_type"] == "alias")
            & (keyvalue_store["field"] == "value")
        )
        .select(
            keyvalue_store["entity_id"].name("hash"),
            keyvalue_store["value"].name("alias"),
        )
        .to_pandas()
    )
    df = yaml_entities.merge(alias_df, on="hash", how="left")

    if csv_spine is not None:
        csv_df = csv_spine.to_pandas()
        csv_entity_df = csv_df[["entity_id", "entity_key", "filepath", "path"]].drop_duplicates()
        csv_entity_df = csv_entity_df.rename(columns={"entity_id": "hash"})
        csv_entity_df["value"] = csv_entity_df["entity_key"]
        csv_entity_df["alias"] = pd.NA
        csv_entity_df = csv_entity_df[["hash", "path", "value", "alias", "entity_key", "filepath"]]
        df = pd.concat([df, csv_entity_df], ignore_index=True)

    df = df[["hash", "path", "value", "alias", "entity_key", "filepath"]]
    for col in ("hash", "path", "value", "entity_key"):
        df[col] = df[col].astype(pd.StringDtype())
    df["alias"] = df["alias"].astype(pd.StringDtype())
    df["filepath"] = df["filepath"].astype(pd.StringDtype())
    return ibis.memtable(df)


def component_type_table(keyvalue_store: ir.Table, csv_spine: ir.Table = None) -> ir.Table:
    """Build one row per component instance from the key-value store and optional CSV spine.

    Returns
    -------
    ir.Table
        Columns: entity_id, component_index, component_type, modifier.
    """
    yaml_ct = keyvalue_store.select(
        "entity_id", "component_index", "component_type", "modifier"
    ).distinct()
    if csv_spine is None:
        return yaml_ct
    csv_ct = csv_spine.select("entity_id", "component_index", "component_type", "modifier")
    return yaml_ct.union(csv_ct)


def component_tables(
    keyvalue_store: ir.Table,
    csv_component_tables: dict[str, ir.Table] = None,
) -> dict[str, ir.Table]:
    """Pivot the key-value store by component type, then merge with CSV component tables.

    YAML-derived tables come from ``keyvalue_store``; CSV-derived tables come
    from ``csv_component_tables``. For component types that appear in both
    sources the rows are unioned (columns are aligned; missing columns in either
    source are filled with NULL). Component types that appear only in one source
    are included as-is.

    Returns
    -------
    dict[str, ir.Table]
        Keys are component types; each value is an ibis Table with columns
        entity_id, component_index, modifier, and one column per field
        (or "value" for scalar components).
    """
    df = keyvalue_store.select(
        "entity_id", "component_index", "component_type", "modifier", "field", "value"
    ).to_pandas()

    result = {}
    for comp_type, group in df.groupby("component_type"):
        instances: dict[tuple, dict] = {}
        for _, row in group.iterrows():
            key = (row["entity_id"], row["component_index"])
            if key not in instances:
                instances[key] = {
                    "entity_id": row["entity_id"],
                    "component_index": row["component_index"],
                    "modifier": row["modifier"],
                }
            instances[key][row["field"]] = row["value"]

        comp_df = pd.DataFrame(list(instances.values()))
        comp_df["modifier"] = comp_df["modifier"].astype(pd.StringDtype())
        result[comp_type] = ibis.memtable(comp_df)

    if csv_component_tables:
        for comp_type, csv_table in csv_component_tables.items():
            if comp_type in result:
                yaml_df = result[comp_type].to_pandas()
                csv_df = csv_table.to_pandas()
                combined = pd.concat([yaml_df, csv_df], ignore_index=True)
                combined["modifier"] = combined["modifier"].astype(pd.StringDtype())
                result[comp_type] = ibis.memtable(combined)
            else:
                result[comp_type] = csv_table

    return result


def registry(
    entity_id_table: ir.Table,
    component_type_table: ir.Table,
    component_tables: dict[str, ir.Table],
) -> Registry:
    """Load the constituents of a registry into the registry object.

    Parameters
    ----------
    entity_id_table : ir.Table
        One row per entity (hash, path, value, alias, entity_key, filepath).
    component_type_table : ir.Table
        One row per component instance (entity_id, component_index, component_type, modifier).
    component_tables : dict[str, ir.Table]
        Per-component-type data tables.

    Returns
    -------
    Registry
        A registry object containing the component tables.
    """
    conn = ibis.duckdb.connect()
    conn.create_table("entity_id", entity_id_table.to_pandas(), overwrite=True)
    conn.create_table("component_type", component_type_table.to_pandas(), overwrite=True)
    components = {
        "entity_id": conn.table("entity_id"),
        "component_type": conn.table("component_type"),
    }
    for comp_type, table in component_tables.items():
        conn.create_table(comp_type, table.to_pandas(), overwrite=True)
        components[comp_type] = conn.table(comp_type)
    return Registry(conn, components)
