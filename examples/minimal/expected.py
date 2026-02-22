import pandas as pd

from iacs.utils import dhash


raw_entity_first_data = {
    "my_requirement": [
        {"description": "A task I need to complete."},
        "requirement",
        {"solution": "my_infrastructure"},
    ],
    "my_infrastructure": [
        {"description": "A task I need to complete."},
    ],
}

pathvalue_pairs = pd.DataFrame(
    [
        ["my_requirement[0].description", "A task I need to complete."],
        ["my_requirement[1].solution", "my_infrastructure"],
        ["my_infrastructure[0].description", "Infrastructure to complete the task."],
    ],
    columns=["path", "value"],
)

spine = pd.DataFrame(
    [
        {
            "entity_id": dhash("my_requirement"),
            "component_index": 0,
            "entity_key": "my_requirement",
            "component_type": "description",
            "modifier": None,
            "path": "my_requirement[0].description",
        },
        {
            "entity_id": dhash("my_requirement"),
            "component_index": 1,
            "entity_key": "my_requirement",
            "component_type": "solution",
            "modifier": None,
            "path": "my_requirement[1].solution",
        },
        {
            "entity_id": dhash("my_infrastructure"),
            "component_index": 0,
            "entity_key": "my_infrastructure",
            "component_type": "description",
            "modifier": None,
            "path": "my_infrastructure[0].description",
        },
    ]
)


hierarchy = pd.DataFrame([], columns=["entity_id", "parent_id"])

incomplete_component_tables = {
    "description": pd.DataFrame(
        [
            {
                "entity_id": dhash("my_requirement"),
                "value": "A task I need to complete.",
            },
            {
                "entity_id": dhash("my_infrastructure"),
                "value": "Infrastructure to complete the task.",
            },
        ]
    ),
    "solution": pd.DataFrame(
        [
            {"entity_id": dhash("my_requirement"), "value": "my_infrastructure"},
        ]
    ),
}

component_tables = incomplete_component_tables
