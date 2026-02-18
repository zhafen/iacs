"""Hamilton DAG for converting entity-centered data to component-centered data."""

from pathlib import Path
from typing import Any

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import pandas as pd
import pydantic
import yaml

from ..registry import Registry


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


def _flatten(data: dict, parent_path: str = "", result: dict | None = None) -> dict:
    """Recursively flatten entity-first data."""
    if result is None:
        result = {}
    for key, value in data.items():
        path = f"{parent_path}.{key}" if parent_path else key
        if isinstance(value, list):
            # Already a flat entity with component list
            components = list(value)
            if parent_path:
                components.append({"parent": parent_path})
            result[path] = components
        elif isinstance(value, dict):
            # May have "data" key for parent's own components
            components = list(value.get("data", []))
            # Add parent component for this child
            if parent_path:
                components.append({"parent": parent_path})
            result[path] = components
            # Recurse into sub-entity keys
            sub = {k: v for k, v in value.items() if k != "data"}
            _flatten(sub, path, result)
    return result


def flattened_entity_first_data(raw_entity_first_data: dict) -> dict:
    """Flatten the raw entity-first data into a dictionary with no hierarchical
    structure. The structure of the data is preserved as ((parent)) components.

    Parameters
    ----------
    raw_entity_first_data : dict
        The input entity-first data

    Returns
    -------
    dict
        Entity-first ECS data with no hierarchical structure.
    """
    return _flatten(raw_entity_first_data)


def _parse_component(entity_id: str, component):
    """Parse a single component item, returning (type, fields_dict)."""
    if isinstance(component, str):
        return component, {}
    elif isinstance(component, dict):
        comp_type = next(iter(component))
        raw_value = component[comp_type]
        if isinstance(raw_value, dict):
            return comp_type, dict(raw_value)
        elif comp_type == "parent":
            return comp_type, {"source": entity_id, "target": raw_value}
        else:
            return comp_type, {"value": raw_value}
    return None, None


@extract_fields(
    {
        "schema": list,
        "parent": list,
    }
)
def component_first_data(flattened_entity_first_data: dict) -> dict[str, list]:
    """Switch the organization of the entity-first data to be component-first.

    Parameters
    ----------
    flattened_entity_first_data : dict

    Returns
    -------
    dict
        Component-first ECS data, i.e. a dictionary of components, each of which is
        a list of component instances.
        The "schema" item is a component containing the schema of all the components.
        The "parent" item records the hierarchy of entities.
    """
    result: dict[str, list] = {}
    for entity_id, components in flattened_entity_first_data.items():
        for component in components:
            comp_type, fields = _parse_component(entity_id, component)
            if comp_type is None:
                continue
            instance = {"entity_id": entity_id, **fields}
            result.setdefault(comp_type, []).append(instance)
    # Ensure required keys exist for @extract_fields
    result.setdefault("schema", [])
    result.setdefault("parent", [])
    return result


def complete_schema(schema: list, parent: list) -> dict:
    """Combine the schema component with the parent component and schema defaults
    to add missing data to the schema. Specifically, schema inherit columns
    from their parents, which they may or may not override.

    Parameters
    ----------
    schema : dict
        The schema component with no inferred values.

    parent : dict
        The parent component, containing relationship information.

    Returns
    -------
    dict
        Fully inferred schema.
    """
    # Build entity_id → columns lookup
    columns_by_id = {}
    parent_by_id = {}
    for entry in schema:
        eid = entry["entity_id"]
        columns_by_id[eid] = dict(entry.get("columns", {}))
        if entry.get("parent") is not None:
            parent_by_id[eid] = entry["parent"]

    # Fallback to parent list for entities without "parent" in schema
    for entry in parent:
        eid = entry["entity_id"]
        if eid not in parent_by_id:
            parent_by_id[eid] = entry["target"]

    # Topologically resolve: merge parent columns as base, child overrides
    resolved = {}

    def resolve(eid):
        if eid in resolved:
            return resolved[eid]
        own_columns = dict(columns_by_id.get(eid, {}))
        parent_eid = parent_by_id.get(eid)
        if parent_eid is not None and parent_eid in columns_by_id:
            parent_cols = dict(resolve(parent_eid))
            parent_cols.update(own_columns)
            resolved[eid] = parent_cols
        else:
            resolved[eid] = own_columns
        return resolved[eid]

    for eid in columns_by_id:
        resolve(eid)

    return resolved


TYPE_MAP = {"str": str, "int": int, "float": float}


def data_models(complete_schema: dict) -> dict[str, pydantic.BaseModel]:
    """Convert the schema into pydantic models.

    Parameters
    ----------
    complete_schema : dict

    Returns
    -------
    dict[str, pydantic.BaseModel]
        A dictionary of pydantic models.
    """
    models = {}
    for comp_type, columns in complete_schema.items():
        fields = {}
        for col_name, col_def in columns.items():
            py_type = TYPE_MAP.get(col_def.get("type", ""), Any)
            fields[col_name] = (py_type, ...)
        models[comp_type] = pydantic.create_model(comp_type, **fields)
    return models


@unpack_fields("conn", "components")
def components_database(
    component_first_data: dict[str, list], data_models: dict[str, pydantic.BaseModel]
) -> tuple[ibis.BaseBackend, dict[str, ibis.Table | dict]]:
    """Convert the component-first data into a components dictionary, where values are
    ibis Tables or dictionaries, depending on the schema.

    Parameters
    ----------
    component_first_data : dict[str, list]

    data_models : dict[str, pydantic.BaseModel]

    Returns
    -------
    conn : ibis.BaseBackend
        An Ibis backend containing the component tables.

    components : dict[str, ibis.Table | dict]
    """
    conn = ibis.duckdb.connect()
    components = {}
    for comp_type, instances in component_first_data.items():
        if not instances:
            continue
        df = pd.DataFrame(instances)
        # Cast object columns to string to avoid DuckDB/pyarrow type errors
        # with non-scalar values (dicts, lists, etc.)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)
        conn.create_table(comp_type, df)
        components[comp_type] = conn.table(comp_type)
    return conn, components


def validated_components(
    components: dict[str, ibis.Table | dict], data_models: dict[str, pydantic.BaseModel]
) -> dict[str, ibis.Table | dict]:
    """Validate the component tables against the pydantic models. The data models
    get stored under the "schema" component.

    Parameters
    ----------
    components : dict[str, ibis.Table | dict]

    data_models : dict[str, pydantic.BaseModel]

    Returns
    -------
    dict[str, ibis.Table | dict]
        The same component tables, but with validation applied.
    """
    for comp_type, table in components.items():
        if comp_type in data_models and isinstance(table, ibis.Table):
            model = data_models[comp_type]
            df = table.to_pandas()
            for _, row in df.iterrows():
                row_dict = {k: v for k, v in row.items() if k != "entity_id"}
                model(**row_dict)
    components["schema"] = data_models
    return components


def registry(
    conn: ibis.BaseBackend, validated_components: dict[str, ibis.Table | dict]
) -> Registry:
    """Convert the components and connection into a registry object.

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
    return Registry(conn, validated_components)
