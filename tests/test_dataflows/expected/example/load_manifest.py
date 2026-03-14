import pandas as pd

from iacs.utils import dhash

filepath = "examples/example/manifest.yaml"


def get_id(path):
    return dhash(f"{filepath}:{path}")


raw_entity_first_data = {
    filepath: {
        "make_cats_happy": {
            "data": [
                {"description": "The mission of our cat-happiness device."},
                {"requirement": {"priority": 1}},
            ],
            "feed_and_water_cats": {
                "data": [
                    {"description": "Obviously."},
                    {"requirement": {"priority": 1}},
                ],
                "feed_cats": [
                    "requirement",
                    {"alias": "feed_cats"},
                ],
                "water_cats": [
                    "requirement",
                    {"alias": "water_cats"},
                ],
            },
            "sift_cat_box": [
                {"description": "Unfortunately."},
                {"requirement": {"priority": 0.8}},
            ],
            "adore_cats": [
                {"description": "Of course."},
                "requirement",
            ],
        },
        "cat_happiness_device": {
            "data": [
                {"description": "An all-in-one tool to make cats happy."},
                {"solution of": "make_cats_happy"},
            ],
            "feeding_system": {
                "data": [
                    {"solution of": "make_cats_happy.feed_and_water_cats"},
                ],
            },
        },
        "cat": [
            {"description": "A data representation of a cat."},
            {
                "field": {
                    "name": "name",
                    "value": "The cat's name.",
                    "type": "str",
                }
            },
            {
                "field": {
                    "name": "breed",
                    "value": "The breed of the cat, e.g. orange.",
                    "type": "str",
                }
            },
        ],
    }
}

pathvalue_pairs = pd.DataFrame(
    [
        [
            f"{filepath}:make_cats_happy.data[0].description",
            "The mission of our cat-happiness device.",
        ],
        [
            f"{filepath}:make_cats_happy.feed_and_water_cats.feed_cats[1].alias",
            "feed_cats",
        ],
        [
            f"{filepath}:cat_happiness_device.feeding_system.feed_cats[2].solution of",
            "make_cats_happy.feed_and_water_cats.feed_cats",
        ],
        ["builtins.components:base_data_type.float[1].description", "Float data type."],
    ],
    columns=["path", "value"],
)

keyvalue_store = pd.DataFrame(
    [
        {
            "entity_id": get_id("make_cats_happy"),
            "component_index": 0,
            "component_type": "description",
            "modifier": None,
            "field": "value",
            "value": "The mission of our cat-happiness device.",
        },
        {
            "entity_id": get_id("make_cats_happy.feed_and_water_cats.feed_cats"),
            "component_index": 1,
            "component_type": "alias",
            "modifier": None,
            "field": "value",
            "value": "feed_cats",
        },
        {
            "entity_id": get_id("cat_happiness_device.feeding_system.feed_cats"),
            "component_index": 2,
            "component_type": "solution",
            "modifier": "of",
            "field": "value",
            "value": "make_cats_happy.feed_and_water_cats.feed_cats",
        },
    ],
)
main_req_id = get_id("make_cats_happy")
feed_cats_req_id = get_id("make_cats_happy.feed_and_water_cats.feed_cats")
feed_cats_soln_id = get_id("cat_happiness_device.feeding_system.feed_cats")

entity_id_table = pd.DataFrame(
    [
        {
            "hash": main_req_id,
            "path": f"{filepath}:make_cats_happy",
            "value": "make_cats_happy",
            "alias": None,
            "entity_key": "make_cats_happy",
            "filepath": filepath,
        },
        {
            "hash": feed_cats_req_id,
            "path": f"{filepath}:make_cats_happy.feed_and_water_cats.feed_cats",
            "value": "feed_and_water_cats.feed_cats",
            "alias": "feed_cats",
            "entity_key": "feed_cats",
            "filepath": filepath,
        },
    ]
)

component_type_table = pd.DataFrame(
    [
        {
            "entity_id": main_req_id,
            "component_index": 0,
            "component_type": "description",
            "modifier": None,
        },
        {
            "entity_id": feed_cats_req_id,
            "component_index": 1,
            "component_type": "alias",
            "modifier": None,
        },
        {
            "entity_id": feed_cats_soln_id,
            "component_index": 2,
            "component_type": "solution",
            "modifier": "of",
        },
    ]
)

component_tables = {
    "description": pd.DataFrame(
        [
            {
                "entity_id": main_req_id,
                "component_index": 0,
                "value": "The mission of our cat-happiness device.",
            }
        ]
    ),
    "requirement": pd.DataFrame(
        [
            {
                "entity_id": main_req_id,
                "component_index": 1,
                "priority": 1.0,
            },
            {
                "entity_id": feed_cats_req_id,
                "component_index": 0,
                "priority": 0.9,
            },
            {
                "entity_id": get_id("make_cats_happy.sift_cat_box"),
                "component_index": 1,
                "priority": 0.8,
            },
        ]
    ),
    "solution": pd.DataFrame(
        [
            {
                "entity_id": get_id("cat_happiness_device"),
                "component_index": 1,
                "modifier": "of",
                "value": "make_cats_happy",
            }
        ]
    ),
    "field": pd.DataFrame(
        [
            {
                "entity_id": get_id("cat"),
                "component_index": 1,
                "value": "name",
                "description": "The cat's name.",
                "type": "str",
            },
            {
                "entity_id": get_id("cat"),
                "component_index": 2,
                "value": "breed",
                "description": "The breed of the cat, e.g. orange.",
                "type": "str",
            },
        ]
    ),
}