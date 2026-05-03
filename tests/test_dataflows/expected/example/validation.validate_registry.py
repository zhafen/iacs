import pandas as pd

from iacs.utils import dhash

filepath = "examples/example/manifest.yaml"


def get_id(path):
    return dhash(f"{filepath}:{path}")

updated_parent = pd.DataFrame(
    [
        {
            "entity_id": get_id("make_cats_happy.feed_and_water_cats.feed_cats"),
            "parent_id": get_id("make_cats_happy.feed_and_water_cats"),
        },
        {
            "entity_id": get_id("make_cats_happy.feed_and_water_cats"),
            "parent_id": get_id("make_cats_happy"),
        },
        {
            "entity_id": get_id("cat_happiness_device.feeding_system.feed_cats"),
            "parent_id": get_id("cat_happiness_device.feeding_system"),
        },
        {
            "entity_id": get_id("cat_happiness_device.feeding_system"),
            "parent_id": get_id("cat_happiness_device"),
        },
    ],
    columns=["entity_id", "parent_id"],
)

validated_field = pd.DataFrame(
    [
        {
            "entity_id": get_id("cat"),
            "component_index": 1,
            "value": "name",
            "description": "The cat's name.",
            "type": "str",
            "nullable": True,
            "unique": True,
            "default": None,
            "range": None,
        },
        {
            "entity_id": get_id("cat"),
            "component_index": 2,
            "value": "breed",
            "description": "The breed of the cat, e.g. orange.",
            "type": "str",
            "nullable": True,
            "unique": False,
            "default": None,
            "range": None,
        },
    ]
)

derived_field = pd.DataFrame(
    [
        {
            "entity_id": get_id("sustenance"),
            "component_index": 1,
            "value": "value",
            "description": "The quantity of the sustenance.",
            "type": "float",
            "nullable": False,
            "unique": False,
            "default": None,
            "range": None,
        },
        {
            "entity_id": get_id("sustenance.food"),
            "component_index": 1,
            "value": "brand",
            "description": "The brand of cat food.",
            "type": "str",
            "nullable": True,
            "unique": False,
            "default": "shiny_sustenance",
            "range": None,
        },
        {
            "entity_id": get_id("sustenance.food"),
            "component_index": 2,
            "value": "type",
            "description": "The type of cat food.",
            "type": "str",
            "nullable": False,
            "unique": False,
            "default": "wet",
            "range": ["wet", "dry"],
        },
        {
            "entity_id": get_id("sustenance.food"),
            "component_index": 3,
            "value": "value",
            "description": "The quantity of the sustenance.",
            "type": "float",
            "nullable": False,
            "unique": False,
            "default": None,
            "range": None,
        },
    ]
)

validated_components = {
    "food": pd.DataFrame([
        {
            "entity_id": get_id("cat_food_supply.shiny_sustenance"),
            "component_index": 1,
            "value": 24.0,
            "brand": "shiny_sustenance",
            "type": "wet",
        },
        {
            "entity_id": get_id("cat_food_supply.furina"),
            "component_index": 1,
            "value": 32.0,
            "brand": "furina",
            "type": "dry",
        },
    ]),
    "requirement": pd.DataFrame([
        {
            "entity_id": get_id("make_cats_happy.adore_cats"),
            "component_index": 1,
            "type": "functional",
            "value": 0.5,
        },
    ]),
}
invalid_field = pd.DataFrame(
    [
        {
            "entity_id": get_id("cat_food_supply.mystery_meat"),
            "component_index": 1,
            "component_type": "food",
            "field": "value",
            "value": None,
            "error_type": "nullable",
        },
        {
            "entity_id": get_id("cat_food_supply.mystery_meat"),
            "component_index": 1,
            "component_type": "food",
            "field": "type",
            "value": "cosmic_horror",
            "error_type": "range",
        },
    ]
)

validated_registry = {
    "requirement": pd.DataFrame([
        {
            "entity_id": get_id("make_cats_happy.feed_and_water_cats.water_cats"),
            "component_index": 0,
            "type": "functional",
            "value": 0.5,
        },
        {
            "entity_id": get_id("make_cats_happy.adore_cats"),
            "component_index": 1,
            "type": "functional",
            "value": 0.5,
        },
    ]),
}
