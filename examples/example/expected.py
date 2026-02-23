import pandas as pd

from iacs.utils import dhash

raw_entity_first_data = {
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

pathvalue_pairs = pd.DataFrame(
    [
        [
            "make_cats_happy.data[0].description",
            "The mission of our cat-happiness device.",
        ],
        [
            "make_cats_happy.feed_and_water_cats.feed_cats[1].alias",
            "feed_cats",
        ],
        [
            "cat_happiness_device.feeding_system.feed_cats[2].solution of",
            "make_cats_happy.feed_and_water_cats.feed_cats",
        ],
    ],
    columns=["path", "value"],
)

spine = pd.DataFrame(
    [
        {
            "entity_id": dhash("make_cats_happy"),
            "component_index": 0,
            "entity_key": "make_cats_happy",
            "component_type": "description",
            "modifier": None,
            "path": "make_cats_happy.data[0].description",
        },
        {
            "entity_id": dhash("make_cats_happy.feed_and_water_cats.feed_cats"),
            "component_index": 1,
            "entity_key": "feed_cats",
            "component_type": "alias",
            "modifier": None,
            "path": "make_cats_happy.feed_and_water_cats.feed_cats[1].alias",
        },
        {
            "entity_id": dhash("cat_happiness_device.feeding_system.feed_cats"),
            "component_index": 2,
            "entity_key": "feed_cats",
            "component_type": "solution",
            "modifier": "of",
            "path": "cat_happiness_device.feeding_system.feed_cats[2].solution of",
        },
    ]
)

hierarchy = pd.DataFrame(
    [
        {
            "entity_id": dhash("make_cats_happy.feed_and_water_cats.feed_cats"),
            "parent_id": dhash("make_cats_happy.feed_and_water_cats"),
        },
        {
            "entity_id": dhash("make_cats_happy.feed_and_water_cats"),
            "parent_id": dhash("make_cats_happy"),
        },
        {
            "entity_id": dhash("cat_happiness_device.feeding_system.feed_cats"),
            "parent_id": dhash("cat_happiness_device.feeding_system"),
        },
        {
            "entity_id": dhash("cat_happiness_device.feeding_system"),
            "parent_id": dhash("cat_happiness_device"),
        },
    ],
    columns=["entity_id", "parent_id"],
)

incomplete_component_tables = {
    "description": pd.DataFrame(
        [
            {
                "entity_id": dhash("make_cats_happy"),
                "component_index": 0,
                "value": "The mission of our cat-happiness device.",
            }
        ]
    ),
    "requirement": pd.DataFrame(
        [
            {
                "entity_id": dhash("make_cats_happy"),
                "component_index": 1,
                "priority": "1",
            },
            {
                "entity_id": dhash("make_cats_happy.feed_and_water_cats.feed_cats"),
                "component_index": 0,
                "priority": None,
            },
            {
                "entity_id": dhash("make_cats_happy.sift_cat_box"),
                "component_index": 1,
                "priority": "0.8",
            },
        ]
    ),
    "solution": pd.DataFrame(
        [
            {
                "entity_id": dhash("cat_happiness_device"),
                "component_index": 1,
                "modifier": "of",
                "value": "make_cats_happy",
            }
        ]
    ),
    "field": pd.DataFrame(
        [
            {
                "entity_id": dhash("cat"),
                "component_index": 1,
                "name": "name",
                "value": "The cat's name.",
                "type": "str",
            },
            {
                "entity_id": dhash("cat"),
                "component_index": 2,
                "name": "breed",
                "value": "The breed of the cat, e.g. orange.",
                "type": "str",
            },
        ]
    ),
}

component_tables = incomplete_component_tables
