"""Hamilton DAG for converting entity-centered data to component-centered data."""

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import pydantic
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

    return


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

    return


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

    return


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

    return


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

    return


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

    return


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

    return


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

    return
