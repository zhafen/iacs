import pandas as pd

from iacs.utils import dhash


raw_entity_first_data = {
    "examples/minimal/minimal.yaml": {
        "my_requirement": [
            {"description": "A task I need to complete."},
            "requirement",
            {"solution": "my_infrastructure"},
        ],
        "my_infrastructure": [
            {"description": "Infrastructure to complete the task."},
        ],
    },
}

# A negative case: this description appears nowhere in the actual data, so
# _assert_not_subset should find that it does NOT match. Exercises the
# `incorrect_` handling in _ExpectedValueChecker.run_after_node_execution.
incorrect_raw_entity_first_data = {
    "examples/minimal/minimal.yaml": {
        "my_requirement": [
            {"description": "This description does not appear anywhere in the actual data."},
        ],
    },
}

pathvalue_pairs = pd.DataFrame(
    [
        ["examples/minimal/minimal.yaml:my_requirement[0].description", "A task I need to complete."],
        ["examples/minimal/minimal.yaml:my_requirement[2].solution", "my_infrastructure"],
        ["examples/minimal/minimal.yaml:my_infrastructure[0].description", "Infrastructure to complete the task."],
    ],
    columns=["path", "value"],
)

entity_id_table = pd.DataFrame(
    [
        {
            "value": dhash("examples/minimal/minimal.yaml:my_requirement"),
            "path": "examples/minimal/minimal.yaml:my_requirement",
            "alias": "my_requirement",
            "entity_key": "my_requirement",
            "filepath": "examples/minimal/minimal.yaml",
        },
        {
            "value": dhash("examples/minimal/minimal.yaml:my_infrastructure"),
            "path": "examples/minimal/minimal.yaml:my_infrastructure",
            "alias": "my_infrastructure",
            "entity_key": "my_infrastructure",
            "filepath": "examples/minimal/minimal.yaml",
        },
    ]
)

component_type_table = pd.DataFrame(
    [
        {
            "entity_id": dhash("examples/minimal/minimal.yaml:my_requirement"),
            "component_index": 0,
            "component_type": "description",
            "modifier": None,
        },
        {
            "entity_id": dhash("examples/minimal/minimal.yaml:my_requirement"),
            "component_index": 2,
            "component_type": "solution",
            "modifier": None,
        },
        {
            "entity_id": dhash("examples/minimal/minimal.yaml:my_infrastructure"),
            "component_index": 0,
            "component_type": "description",
            "modifier": None,
        },
    ]
)

component_tables = {
    "description": pd.DataFrame(
        [
            {
                "entity_id": dhash("examples/minimal/minimal.yaml:my_requirement"),
                "value": "A task I need to complete.",
            },
            {
                "entity_id": dhash("examples/minimal/minimal.yaml:my_infrastructure"),
                "value": "Infrastructure to complete the task.",
            },
        ]
    ),
    "solution": pd.DataFrame(
        [
            {"entity_id": dhash("examples/minimal/minimal.yaml:my_requirement"), "value": "my_infrastructure"},
        ]
    ),
}
