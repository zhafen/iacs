"""Hamilton DAG for converting entity-centered data to component-centered data.

Coordinates load_yaml and load_python subdags, merges their entity-first
dictionaries, then runs the shared pipeline through to a Registry.
"""

import re
from pathlib import Path

import ibis
import ibis.expr.types as ir
import pandas as pd
from hamilton.function_modifiers import subdag, source

from ...registry import Registry
from ...utils import dhash
from . import load_yaml, load_python


# ---------------------------------------------------------------------------
# Source subdags — each produces raw_entity_first_data keyed by file_id
# ---------------------------------------------------------------------------

@subdag(
    load_yaml,
    inputs={"input_dir": source("input_dir")},
    config={},
)
def yaml_entity_first_data(raw_entity_first_data: dict) -> dict:
    return raw_entity_first_data


@subdag(
    load_python,
    inputs={"input_dir": source("input_dir")},
    config={},
)
def python_entity_first_data(raw_entity_first_data: dict) -> dict:
    return raw_entity_first_data


def raw_entity_first_data(
    yaml_entity_first_data: dict,
    python_entity_first_data: dict,
) -> dict:
    """Merge entity-first dicts from all source loaders."""
    return {**yaml_entity_first_data, **python_entity_first_data}


# ---------------------------------------------------------------------------
# CSV loading (stays inline — CSV doesn't fit the entity-first dict format)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Shared pipeline: entity-first dict → component tables → Registry
# ---------------------------------------------------------------------------

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
        The raw component value.
    result : list
        Accumulator of (path, value) string tuples.
    """
    prefix = f"{entity_path}[{index}]"
    if isinstance(component, str):
        result.append((f"{prefix}.{component}", ""))
    elif isinstance(component, dict):
        key = next(iter(component))
        value = component[key]
        if isinstance(value, list):
            for j, item in enumerate(value):
                item_prefix = f"{entity_path}[{index + j}]"
                if isinstance(item, dict):
                    for sub_key, sub_val in item.items():
                        str_val = "" if sub_val is None else str(sub_val)
                        result.append((f"{item_prefix}.{key}.{sub_key}", str_val))
                else:
                    str_val = "" if item is None else str(item)
                    result.append((f"{item_prefix}.{key}", str_val))
        elif isinstance(value, dict) and value and all(
            isinstance(v, dict) for v in value.values()
        ):
            for j, (inner_key, inner_dict) in enumerate(value.items()):
                item_prefix = f"{entity_path}[{index + j}]"
                result.append((f"{item_prefix}.{key}.value", inner_key))
                for sub_key, sub_val in inner_dict.items():
                    str_val = "" if sub_val is None else str(sub_val)
                    result.append((f"{item_prefix}.{key}.{sub_key}", str_val))
        elif isinstance(value, dict):
            for sub_key, sub_val in value.items():
                str_val = "" if sub_val is None else str(sub_val)
                result.append((f"{prefix}.{key}.{sub_key}", str_val))
        else:
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
            for i, component in enumerate(entity_value.get("data", [])):
                _add_component_pairs(f"{entity_path}.data", i, component, result)
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
    t = t.mutate(
        entity_id=t.entity_path.hexdigest("sha256").substr(0, 12),
        entity_key=t.entity_path.re_extract(r"([^:.]+)$", 1),
        filepath=t.entity_path.re_extract(r"^([^:]+):", 1).nullif(""),
    )
    t = t.mutate(
        field=ibis.ifelse(
            t["path"] == t["spine_path"],
            ibis.literal("value"),
            t["path"].substr(t["spine_path"].length() + 1),
        )
    )
    t = t.mutate(
        field=ibis.ifelse(t["field"] == "", ibis.literal("value"), t["field"])
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
        Columns: value, path, alias, entity_key, filepath.
        ``value`` is the entity hash (the entity_id); ``path`` is the full
        entity_path; ``alias`` is the human-readable display ID (last two
        dot-segments of the entity path, or just entity_key for top-level).
    """
    yaml_entities = keyvalue_store.select(
        "entity_id", "entity_key", "entity_path", "filepath"
    ).distinct().to_pandas()
    yaml_entities = yaml_entities.rename(columns={"entity_id": "value", "entity_path": "path"})

    def compute_alias(row):
        entity_path = row["path"]
        entity_key = row["entity_key"]
        sep = entity_path.find(":")
        name_part = entity_path[sep + 1:] if sep != -1 else entity_path
        parts = name_part.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else entity_key

    yaml_entities["alias"] = yaml_entities.apply(compute_alias, axis=1)
    df = yaml_entities[["value", "path", "alias", "entity_key", "filepath"]]

    if csv_spine is not None:
        csv_df = csv_spine.to_pandas()
        csv_entity_df = csv_df[["entity_id", "entity_key", "filepath", "path"]].drop_duplicates()
        csv_entity_df = csv_entity_df.rename(columns={"entity_id": "value"})
        csv_entity_df["alias"] = csv_entity_df["entity_key"]
        csv_entity_df = csv_entity_df[["value", "path", "alias", "entity_key", "filepath"]]
        df = pd.concat([df, csv_entity_df], ignore_index=True)

    df = df[["value", "path", "alias", "entity_key", "filepath"]]
    for col in ("value", "path", "alias", "entity_key"):
        df[col] = df[col].astype(pd.StringDtype())
    df["filepath"] = df["filepath"].astype(pd.StringDtype())
    return ibis.memtable(df)


def component_type_table(keyvalue_store: ir.Table, csv_spine: ir.Table = None) -> ir.Table:
    """Build one row per component instance, including derived and skip_on_export flags.

    Reads explicit ``component_type`` component entries from the keyvalue_store to
    populate ``derived`` and ``skip_on_export`` columns on the metadata table.

    Returns
    -------
    ir.Table
        Columns: entity_id, component_index, component_type, modifier, derived, skip_on_export.
    """
    df = keyvalue_store.execute()

    entity_keys = (
        df[["entity_id", "entity_key"]]
        .drop_duplicates(subset=["entity_id"])
        .set_index("entity_id")["entity_key"]
        .to_dict()
    )

    ct_data = df[df["component_type"] == "component_type"]
    derived_set: set[str] = set()
    skip_set: set[str] = set()
    for _, row in ct_data.iterrows():
        eid = str(row["entity_id"])
        field = str(row["field"])
        val = str(row.get("value", "")).strip().lower() in ("true", "1", "yes")
        type_name = entity_keys.get(eid, "")
        if not type_name:
            continue
        if field == "derived" and val:
            derived_set.add(type_name)
        elif field == "skip_on_export" and val:
            skip_set.add(type_name)

    meta_df = df[["entity_id", "component_index", "component_type", "modifier"]].drop_duplicates().copy()
    meta_df["derived"] = meta_df["component_type"].isin(derived_set)
    meta_df["skip_on_export"] = meta_df["component_type"].isin(skip_set)
    meta_df["modifier"] = meta_df["modifier"].astype(pd.StringDtype())
    yaml_ct = ibis.memtable(meta_df)

    if csv_spine is None:
        return yaml_ct

    csv_df = csv_spine.to_pandas()[["entity_id", "component_index", "component_type", "modifier"]].copy()
    csv_df["derived"] = False
    csv_df["skip_on_export"] = False
    csv_df["modifier"] = csv_df["modifier"].astype(pd.StringDtype())
    return ibis.union(yaml_ct, ibis.memtable(csv_df))


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


def authored_parent(component_tables: dict) -> ir.Table:
    """Extract the authored (user-written) parent entries before updated_parent() modifies them.

    Parameters
    ----------
    component_tables : dict
        Per-component-type data tables as produced by ``component_tables``.

    Returns
    -------
    ir.Table
        The raw ``parent`` table from component_tables if it exists, otherwise
        an empty ibis table with columns entity_id, component_index, modifier, value.
    """
    if "parent" in component_tables:
        return component_tables["parent"]
    empty_df = pd.DataFrame(columns=["entity_id", "component_index", "modifier", "value"])
    empty_df["entity_id"] = empty_df["entity_id"].astype(pd.StringDtype())
    empty_df["component_index"] = empty_df["component_index"].astype("int32")
    empty_df["modifier"] = empty_df["modifier"].astype(pd.StringDtype())
    empty_df["value"] = empty_df["value"].astype(pd.StringDtype())
    return ibis.memtable(empty_df)


def registry(
    entity_id_table: ir.Table,
    component_type_table: ir.Table,
    component_tables: dict[str, ir.Table],
    authored_parent: ir.Table = None,
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
        if comp_type == "component_type":
            continue  # flags already incorporated into component_type_table
        conn.create_table(comp_type, table.to_pandas(), overwrite=True)
        components[comp_type] = conn.table(comp_type)
    if authored_parent is not None:
        conn.create_table("authored_parent", authored_parent.to_pandas(), overwrite=True)
        components["authored_parent"] = conn.table("authored_parent")
    return Registry(conn, components)
