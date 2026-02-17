"""Hamilton DAG for converting entity-centered data to component-centered data."""

from hamilton.function_modifiers import extract_fields
import ibis
import pydantic


def raw_entity_first_dict(input_dir: str) -> dict:

    return

@extract_fields({
    "schema": dict,
})
def component_first_dict(raw_entity_first_dict: dict) -> dict:

    return

def pydantic_models(schema: dict) -> dict[pydantic.BaseModel]:

    return


def raw_component_database(component_first_dict: dict) -> ibis.BaseBackend:

    return


def component_database(
    raw_component_database: ibis.BaseBackend, pydantic_models: dict
) -> ibis.BaseBackend:

    return
