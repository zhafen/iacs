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


def spine(pathvalue_pairs: ir.Table) -> ir.Table:
    """Hash the paths into entity IDs, and extract the parent-child relationships
    and component types.

    Parameters
    ----------
    pathvalue_pairs : ir.Table
    db_conn : ibis.BaseBackend

    Returns
    -------
    spine : ir.Table
        The spine is the shared index of the registry that contains one row per
        component instance, with the entity_id, component type, and original path.
        The entity_id and component_index columns are the actual index of the registry, and the component_type column is used to pivot into component tables.
        It has the below columns:
        - entity_id: the hashed ID of the entity
        - component_index: Index of the component in the original list of components for that entity (derived from the path)
        - entity_key: The name of the entity, the last part of the path for an entity.
        - component_type: the type of the component
        - modifier: any modifiers for the component instance, which may affect interpretation of the fields (e.g. "parent" vs "parent of")
        - filepath: the file identifier of the source file (everything before the ':' in the path), or NULL if no file prefix is present
        - path: the original path
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
    return t.select(
        "entity_id", "component_index", "entity_key", "component_type", "modifier",
        "filepath", t.spine_path.name("path"),
    ).distinct()


def component_tables(
    pathvalue_pairs: ir.Table,
    spine: ir.Table,
) -> dict[str, ir.Table]:
    """Join the pathvalue_pairs and spine on path and group the results by component
    type to create a dictionary of component tables.

    Parameters
    ----------
    db_conn : ibis.BaseBackend
    pathvalue_pairs : ir.Table
    spine : ir.Table

    Returns
    -------
    dict[str, ir.Table]
        Keys are component types; each value is an ibis Table with columns
        entity_id, component_index, modifier, and one column per sub-field
        (or "value" for scalar components).
    """
    # Add spine_path to every matching pvp row using the same ibis expression logic.
    pvp = pathvalue_pairs.filter(pathvalue_pairs.path.re_search(_PATH_PATTERN))
    pvp = _with_spine_path(pvp)

    # Join pvp to spine on spine_path == spine.path.
    spine_for_join = spine.rename(spine_path="path").select(
        "entity_id", "component_index", "component_type", "modifier", "spine_path"
    )
    joined = pvp.join(spine_for_join, "spine_path")

    # field_name: sub-field suffix after the spine_path, or "value" for scalar components.
    joined = joined.mutate(
        field_name=ibis.ifelse(
            joined["path"] == joined["spine_path"],
            "value",
            joined["path"].substr(joined["spine_path"].length() + 1),
        )
    ).select("entity_id", "component_index", "component_type", "modifier", "field_name", "value")

    # Dynamic pivot: one column per field_name. Cannot be expressed as a static ibis
    # expression because column names depend on data, so we drop to pandas here.
    df = joined.to_pandas()

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
            instances[key][row["field_name"]] = row["value"]

        comp_df = pd.DataFrame(list(instances.values()))
        comp_df["modifier"] = comp_df["modifier"].astype(pd.StringDtype())
        result[comp_type] = ibis.memtable(comp_df)

    return result


_ENTITY_PATH_PATTERN = re.compile(r"^(.+?)\[\d+\]\..+$")


def updated_parent(spine: ir.Table) -> pd.DataFrame:
    """Extract parent-child relationships from nested entity paths in the spine.

    Parameters
    ----------
    spine : ir.Table

    Returns
    -------
    pd.DataFrame
        Columns: entity_id, parent_id. One row per nested entity, giving the
        hashed ID of the entity and the hashed ID of its immediate parent.
    """
    df = spine.to_pandas()

    def extract_entity_path(path):
        m = _ENTITY_PATH_PATTERN.match(path)
        if not m:
            return None
        prefix = m.group(1)
        return prefix[:-5] if prefix.endswith(".data") else prefix

    def has_parent(entity_path):
        # Only dots after the ':' file-id separator count as nesting.
        sep = entity_path.find(":")
        name_part = entity_path[sep + 1:] if sep != -1 else entity_path
        return "." in name_part

    def get_parent_path(entity_path):
        sep = entity_path.find(":")
        if sep != -1:
            file_id, name_part = entity_path[:sep], entity_path[sep + 1:]
            return f"{file_id}:{name_part.rsplit('.', 1)[0]}"
        return entity_path.rsplit(".", 1)[0]

    df["entity_path"] = df["path"].apply(extract_entity_path)
    pairs = df[["entity_id", "entity_path"]].dropna().drop_duplicates()
    nested = pairs[pairs["entity_path"].apply(has_parent)].copy()

    if nested.empty:
        return pd.DataFrame([], columns=["entity_id", "parent_id"])

    nested["parent_id"] = nested["entity_path"].apply(
        lambda ep: dhash(get_parent_path(ep))
    )
    return nested[["entity_id", "parent_id"]].reset_index(drop=True)


def registry(spine: ir.Table, component_tables: dict[str, ir.Table]) -> Registry:
    """Load the constituents of a registry into the registry object. The spine is used as the shared index for the registry, and the component tables are attached to it.

    Parameters
    ----------
    component_tables : dict[str, ir.Table]

    Returns
    -------
    Registry
        A registry object containing the component tables.
    """
    conn = ibis.duckdb.connect()
    conn.create_table("spine", spine.to_pandas(), overwrite=True)
    components = {"spine": conn.table("spine")}
    for comp_type, table in component_tables.items():
        conn.create_table(comp_type, table.to_pandas(), overwrite=True)
        components[comp_type] = conn.table(comp_type)
    return Registry(conn, components)
