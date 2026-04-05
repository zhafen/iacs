import pandas as pd

from iacs.utils import get_id as base_get_id

filepath = "examples/example/manifest.yaml"

def get_id(path: str) -> str:

    return base_get_id(filepath, path)

priority_product = pd.DataFrame([
    {"entity_id": get_id("make_cats_happy.feed_and_water_cats"),            "priority_product": 1.0},
    {"entity_id": get_id("make_cats_happy.feed_and_water_cats.feed_cats"),  "priority_product": 0.9},
    {"entity_id": get_id("make_cats_happy.sift_cat_box"),                   "priority_product": 0.8},
])

effort_sum = pd.DataFrame([
    {"entity_id": get_id("cat_happiness_device.feeding_system.feed_cats"), "value": 8.0},
    {"entity_id": get_id("cat_happiness_device.feeding_system.feed_cats"), "value": 2.0, "schedule": "weekly"},
    {"entity_id": get_id("cat_happiness_device.feeding_system.water_cats"), "value": 5.0},
    {"entity_id": get_id("cat_happiness_device.feeding_system.water_cats"), "value": 1.0, "schedule": "2 days"},
    {"entity_id": get_id("cat_happiness_device.feeding_system"), "value": 15.0},
    {"entity_id": get_id("cat_happiness_device.feeding_system"), "value": 2.0, "schedule": "weekly"},
    {"entity_id": get_id("cat_happiness_device.feeding_system"), "value": 1.0, "schedule": "2 days"},
    {"entity_id": get_id("cat_happiness_device"), "value": 15.0},
    {"entity_id": get_id("cat_happiness_device"), "value": 2.0, "schedule": "weekly"},
    {"entity_id": get_id("cat_happiness_device"), "value": 1.0, "schedule": "2 days"},
])
