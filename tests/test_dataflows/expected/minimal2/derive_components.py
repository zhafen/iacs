import pandas as pd

from iacs.utils import get_id as base_get_id

filepath = "examples/minimal2/minimal2.yaml"

def get_id(path: str) -> str:

    return base_get_id(filepath, path)

components_with_resolved_paths = {
    "solution": pd.DataFrame([
        {
            "entity_id": get_id("my_infrastructure.infrastructure_for_first_requirement"),
            "target_path": "core_requirement.first_subrequirement",
            "target_id": get_id("core_requirement.first_subrequirement"),
            "modifier": "of",
        },
        {
            "entity_id": get_id("my_infrastructure.infrastructure_for_second_requirement"),
            "target_path": "...core_requirement.second_subrequirement",
            "target_id": get_id("core_requirement.second_subrequirement"),
            "modifier": "of",
        }
    ])
}
