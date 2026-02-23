"""Hamilton DAG for converting entity-centered data to component-centered data."""

import hashlib
import re
from pathlib import Path
from typing import Any

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import pandas as pd
import pydantic
import yaml

from ..registry import Registry
from ..utils import dhash


def raw_entity_first_data(input_dir: str) -> dict:
    """Load all yaml files from the input directory and its sub directories.

    Parameters
    ----------
    input_dir : str

    Returns
    -------
    dict
        A dictionary containing all the entities from across the files,
        with no transformations applied.
    """
    result = {}
    for path in Path(input_dir).rglob("*.y*ml"):
        if path.suffix in (".yaml", ".yml"):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            result.update(data)
    return result


def db_conn() -> ibis.BaseBackend:
    """Create an Ibis database connection for the data to be stored in.

    Returns
    -------
    ibis.BaseBackend
        An Ibis backend containing the component tables.
    """
    return ibis.duckdb.connect()


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


def pathvalue_pairs(raw_entity_first_data: dict, db_conn: ibis.BaseBackend) -> ibis.Table:
    """Convert the raw entity-first data into a database table with two fields:
    path and value, both of type str. This is the first step in the transformation
    process, and serves as a way to inspect the raw data in a tabular format before
    applying the more complex transformations.

    Parameters
    ----------
    raw_entity_first_data : dict
    conn : ibis.BaseBackend

    Returns
    -------
    ibis.Table
        A table with columns "path" and "value", where "path" is the entity path
        (e.g. "a.b.c[0].key") and "value" is the corresponding leaf value from
        the raw data, serialized as a string.
    """
    pairs = _flatten_to_pathvalue(raw_entity_first_data)
    df = pd.DataFrame(pairs, columns=["path", "value"])
    db_conn.create_table("pathvalue_pairs", df, overwrite=True)
    return db_conn.table("pathvalue_pairs")


_PATH_RE = re.compile(r"^(.+)\[(\d+)\]\.(.+)$")


def _parse_one_path(path: str) -> dict | None:
    """Parse a path string into spine fields.

    Returns a dict with spine columns plus 'entity_path' (for hierarchy) and
    '_spine_path' (for deduplication), or None if the path does not match
    the expected ``entity_prefix[index].component_type`` format.
    """
    m = _PATH_RE.match(path)
    if not m:
        return None
    entity_prefix, idx_str, after = m.group(1), m.group(2), m.group(3)

    # First dot-segment of 'after' is the full component type (may contain spaces).
    component_type_full = after.split(".")[0]

    # Strip the '.data' suffix added for nested entities' own components.
    if entity_prefix.endswith(".data"):
        entity_path = entity_prefix[:-5]
    else:
        entity_path = entity_prefix

    # Split 'solution of' → type='solution', modifier='of'.
    parts = component_type_full.split(" ", 1)
    component_type = parts[0]
    modifier = parts[1] if len(parts) > 1 else None

    spine_path = f"{entity_prefix}[{idx_str}].{component_type_full}"

    return {
        "entity_id": dhash(entity_path),
        "component_index": int(idx_str),
        "entity_key": entity_path.split(".")[-1],
        "component_type": component_type,
        "modifier": modifier,
        "path": spine_path,
        "entity_path": entity_path,
        "_spine_path": spine_path,
    }


@unpack_fields("spine", "hierarchy")
def parsed_paths(pathvalue_pairs: ibis.Table) -> tuple[ibis.Table, ibis.Table]:
    """Hash the paths into entity IDs, and extract the parent-child relationships
    and component types.

    Parameters
    ----------
    pathvalue_pairs : ibis.Table

    Returns
    -------
    spine : ibis.Table
        The spine is the shared index of the registry that contains one row per
        component instance, with the entity_id, component type, and original path.
        The entity_id and component_index columns are the actual index of the registry, and the component_type column is used to pivot into component tables.
        It has the below columns:
        - entity_id: the hashed ID of the entity
        - component_index: Index of the component in the original list of components for that entity (derived from the path)
        - entity_key: The name of the entity, the last part of the path for an entity.
        - component_type: the type of the component
        - modifier: any modifiers for the component instance, which may affect interpretation of the fields (e.g. "parent" vs "parent of")
        - path: the original path

    hierarchy : ibis.Table
        The parent-child relationships between entities as encoded in the paths.
        Note that the ((parent)) component instances in the pathvalue_pairs
        may encode additional relationships.
        A table with the below columns:
        - entity_id: the hashed ID of the entity (derived from the path)
        - parent_id: the hashed ID of the parent entity (derived from the parent path)
    """
    SPINE_COLS = [
        "entity_id", "component_index", "entity_key",
        "component_type", "modifier", "path",
    ]

    df = pathvalue_pairs.to_pandas()

    spine_rows: list[dict] = []
    seen_spine: set[str] = set()
    entity_paths: list[str] = []
    seen_entity_paths: set[str] = set()

    for path in df["path"]:
        row = _parse_one_path(path)
        if row is None:
            continue
        sp = row["_spine_path"]
        if sp not in seen_spine:
            seen_spine.add(sp)
            spine_rows.append(row)
        ep = row["entity_path"]
        if ep not in seen_entity_paths:
            seen_entity_paths.add(ep)
            entity_paths.append(ep)

    spine_df = (
        pd.DataFrame(spine_rows)[SPINE_COLS]
        if spine_rows
        else pd.DataFrame(columns=SPINE_COLS)
    )

    hierarchy_rows = []
    for ep in entity_paths:
        if "." not in ep:
            continue
        parent_path = ep.rsplit(".", 1)[0]
        if parent_path in seen_entity_paths:
            hierarchy_rows.append({
                "entity_id": dhash(ep),
                "parent_id": dhash(parent_path),
            })

    hierarchy_df = pd.DataFrame(
        hierarchy_rows if hierarchy_rows else [],
        columns=["entity_id", "parent_id"],
    )

    return ibis.memtable(spine_df), ibis.memtable(hierarchy_df)

def incomplete_component_tables(
    db_conn: ibis.BaseBackend,
    pathvalue_pairs: ibis.Table,
    spine: ibis.Table,
) -> dict[str, ibis.Table]:
    """Join the pathvalue_pairs and spine on path and group the results by component
    type to create a dictionary of component tables. The result is "incomplete" because
    it doesn't incorporate information from the hierarchy yet.

    Parameters
    ----------
    conn : ibis.BaseBackend
        An Ibis backend containing the component tables.

    validated_components : dict[str, ibis.Table | dict]

    Returns
    -------
    Registry
        A registry object.
    """
    return

def component_tables(
    incomplete_component_tables: dict[str, ibis.Table],
    hierarchy: ibis.Table
) -> dict[str, ibis.Table]:
    """Incorporate the hierarchy information into the component tables by unioning it
    with the parent component table.

    Parameters
    ----------
    incomplete_component_tables : dict[str, ibis.Table]

    Returns
    -------
    dict[str, ibis.Table]
        A dictionary of component tables, ready to be loaded into the registry.
    """
    return

def registry(db_conn: ibis.BaseBackend, spine: ibis.Table, component_tables: dict[str, ibis.Table]) -> Registry:
    """Load the constituents of a registry into the registry object. The spine is used as the shared index for the registry, and the component tables are attached to it.

    Parameters
    ----------
    component_tables : dict[str, ibis.Table]

    Returns
    -------
    Registry
        A registry object containing the component tables.
    """
    return

# def _flatten(
#     data: dict,
#     parent_path: str = "",
#     result: dict | None = None,
#     name_to_id: dict | None = None,
# ) -> tuple[dict, dict]:
#     """Recursively flatten entity-first data, using hashed entity IDs.
# 
#     Metadata
#     --------
#     - todo: We probably don't need an entirely separate name_to_id. We can just store the original path in the ID component...
#     """
#     if result is None:
#         result = {}
#     if name_to_id is None:
#         name_to_id = {}
#     for key, value in data.items():
#         path = f"{parent_path}.{key}" if parent_path else key
#         entity_id = _hash_path(path)
#         name_to_id[key] = entity_id
#         name_to_id[path] = entity_id
#         parent_id = _hash_path(parent_path) if parent_path else None
#         if isinstance(value, list):
#             components = list(value)
#             if parent_id is not None:
#                 components.append({"parent": parent_id})
#             result[entity_id] = components
#         elif isinstance(value, dict):
#             components = list(value.get("data", []))
#             if parent_id is not None:
#                 components.append({"parent": parent_id})
#             result[entity_id] = components
#             sub = {k: v for k, v in value.items() if k != "data"}
#             _flatten(sub, path, result, name_to_id)
#     return result, name_to_id


# Commenting out old code for now to start simpler.
# @extract_fields(
#     {
#         "flattened_data": dict,
#         "name_to_id": dict,
#     }
# )
# def flattened_entity_first_data(raw_entity_first_data: dict) -> dict:
#     """Flatten the raw entity-first data into a dictionary with no hierarchical
#     structure. The structure of the data is preserved as ((parent)) components.
# 
#     Parameters
#     ----------
#     raw_entity_first_data : dict
#         The input entity-first data
# 
#     Returns
#     -------
#     dict
#         Contains 'flattened_data' (entity-first ECS data with no hierarchical
#         structure, using hashed entity IDs) and 'name_to_id' (mapping from
#         original names/paths to hashed IDs).
#     """
#     flattened_data, name_to_id = _flatten(raw_entity_first_data)
#     return {"flattened_data": flattened_data, "name_to_id": name_to_id}
# 
# 
# def _parse_component(entity_id: str, component):
#     """Parse a single component item, returning (type, fields_dict)."""
#     if isinstance(component, str):
#         return component, {}
#     elif isinstance(component, dict):
#         comp_type = next(iter(component))
#         raw_value = component[comp_type]
#         if isinstance(raw_value, dict):
#             return comp_type, dict(raw_value)
#         elif comp_type == "parent":
#             return comp_type, {"source": entity_id, "target": raw_value}
#         elif comp_type == "parent of":
#             return "parent", {"entity_id": raw_value, "source": raw_value, "target": entity_id}
#         else:
#             return comp_type, {"value": raw_value}
#     return None, None
# 
# 
# @extract_fields(
#     {
#         "schema": list,
#         "parent": list,
#     }
# )
# def component_first_data(flattened_data: dict, name_to_id: dict) -> dict[str, list]:
#     """Switch the organization of the entity-first data to be component-first.
# 
#     Parameters
#     ----------
#     flattened_data : dict
#         Flattened entity-first data with hashed entity IDs as keys.
# 
#     name_to_id : dict
#         Mapping from original entity names/paths to hashed IDs.
# 
#     Returns
#     -------
#     dict
#         Component-first ECS data, i.e. a dictionary of components, each of which is
#         a list of component instances.
#         The "schema" item is a component containing the schema of all the components.
#         The "parent" item records the hierarchy of entities.
#         The "name" item stores the original name for each entity.
#     """
#     result: dict[str, list] = {}
#     # Build reverse mapping: hashed_id -> original path (use longest path)
#     id_to_name = {}
#     for name, hid in name_to_id.items():
#         if hid not in id_to_name or len(name) > len(id_to_name[hid]):
#             id_to_name[hid] = name
# 
#     for entity_id, components in flattened_data.items():
#         # Add a name component for human readability
#         if entity_id in id_to_name:
#             result.setdefault("name", []).append(
#                 {"entity_id": entity_id, "value": id_to_name[entity_id]}
#             )
#         for component in components:
#             comp_type, fields = _parse_component(entity_id, component)
#             if comp_type is None:
#                 continue
#             instance = {"entity_id": entity_id, **fields}
#             result.setdefault(comp_type, []).append(instance)
# 
#     # Resolve name references to hashed IDs in entity_id/target/value/source fields
#     for comp_type, instances in result.items():
#         if comp_type == "name":
#             continue
#         for instance in instances:
#             for field in ("entity_id", "target", "value", "source"):
#                 if field in instance and isinstance(instance[field], str):
#                     ref = instance[field]
#                     if ref in name_to_id:
#                         instance[field] = name_to_id[ref]
# 
#     # Ensure required keys exist for @extract_fields
#     result.setdefault("schema", [])
#     result.setdefault("parent", [])
#     return result


# def complete_schema(schema: list, parent: list) -> dict:
#     """Combine the schema component with the parent component and schema defaults
#     to add missing data to the schema. Specifically, schema inherit columns
#     from their parents, which they may or may not override.
# 
#     Parameters
#     ----------
#     schema : dict
#         The schema component with no inferred values.
# 
#     parent : dict
#         The parent component, containing relationship information.
# 
#     Returns
#     -------
#     dict
#         Fully inferred schema.
#     """
#     # Build entity_id → columns lookup
#     columns_by_id = {}
#     parent_by_id = {}
#     for entry in schema:
#         eid = entry["entity_id"]
#         columns_by_id[eid] = dict(entry.get("columns", {}))
#         if entry.get("parent") is not None:
#             parent_by_id[eid] = entry["parent"]
# 
#     # Fallback to parent list for entities without "parent" in schema
#     for entry in parent:
#         eid = entry["entity_id"]
#         if eid not in parent_by_id:
#             parent_by_id[eid] = entry["target"]
# 
#     # Topologically resolve: merge parent columns as base, child overrides
#     resolved = {}
# 
#     def resolve(eid):
#         if eid in resolved:
#             return resolved[eid]
#         own_columns = dict(columns_by_id.get(eid, {}))
#         parent_eid = parent_by_id.get(eid)
#         if parent_eid is not None and parent_eid in columns_by_id:
#             parent_cols = dict(resolve(parent_eid))
#             parent_cols.update(own_columns)
#             resolved[eid] = parent_cols
#         else:
#             resolved[eid] = own_columns
#         return resolved[eid]
# 
#     for eid in columns_by_id:
#         resolve(eid)
# 
#     return resolved
# 
# 
# TYPE_MAP = {"str": str, "int": int, "float": float}
# 
# 
# def data_models(complete_schema: dict) -> dict[str, pydantic.BaseModel]:
#     """Convert the schema into pydantic models.
# 
#     Parameters
#     ----------
#     complete_schema : dict
# 
#     Returns
#     -------
#     dict[str, pydantic.BaseModel]
#         A dictionary of pydantic models.
#     """
#     models = {}
#     for comp_type, columns in complete_schema.items():
#         fields = {}
#         for col_name, col_def in columns.items():
#             py_type = TYPE_MAP.get(col_def.get("type", ""), Any)
#             fields[col_name] = (py_type, ...)
#         models[comp_type] = pydantic.create_model(comp_type, **fields)
#     return models
# 
# 
# @unpack_fields("conn", "components")
# def components_database(
#     component_first_data: dict[str, list], data_models: dict[str, pydantic.BaseModel]
# ) -> tuple[ibis.BaseBackend, dict[str, ibis.Table | dict]]:
#     """Convert the component-first data into a components dictionary, where values are
#     ibis Tables or dictionaries, depending on the schema.
# 
#     Parameters
#     ----------
#     component_first_data : dict[str, list]
# 
#     data_models : dict[str, pydantic.BaseModel]
# 
#     Returns
#     -------
#     conn : ibis.BaseBackend
#         An Ibis backend containing the component tables.
# 
#     components : dict[str, ibis.Table | dict]
# 
#     Metadata
#     --------
#     - todo: This isn't actually using the data models to check if a table is complex or not...
#     """
#     conn = ibis.duckdb.connect()
#     components = {}
#     for comp_type, instances in component_first_data.items():
#         if not instances:
#             continue
#         # Check if any instance has dict/list values — keep as raw list if so
#         has_complex = any(
#             isinstance(v, (dict, list))
#             for inst in instances
#             for k, v in inst.items()
#             if k != "entity_id"
#         )
#         if has_complex:
#             components[comp_type] = instances
#             continue
#         df = pd.DataFrame(instances)
#         for col in df.columns:
#             if df[col].dtype == object:
#                 df[col] = df[col].astype(str)
#         conn.create_table(comp_type, df)
#         components[comp_type] = conn.table(comp_type)
#     return conn, components
# 
# 
# def validated_components(
#     components: dict[str, ibis.Table | dict], data_models: dict[str, pydantic.BaseModel]
# ) -> dict[str, ibis.Table | dict]:
#     """Validate the component tables against the pydantic models. The data models
#     get stored under the "schema" component.
# 
#     Parameters
#     ----------
#     components : dict[str, ibis.Table | dict]
# 
#     data_models : dict[str, pydantic.BaseModel]
# 
#     Returns
#     -------
#     dict[str, ibis.Table | dict]
#         The same component tables, but with validation applied.
# 
#     Metadata
#     --------
#     - todo: Don't do a damn pandas round trip just for validation.
#     """
#     for comp_type, table in components.items():
#         if comp_type in data_models and isinstance(table, ibis.Table):
#             model = data_models[comp_type]
#             df = table.to_pandas()
#             for _, row in df.iterrows():
#                 row_dict = {k: v for k, v in row.items() if k != "entity_id"}
#                 model(**row_dict)
#     components["schema"] = data_models
#     return components