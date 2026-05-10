import pandas as pd

from iacs.utils import get_id

filepath = "examples/example/manifest.yaml"

requirement_coverage = pd.DataFrame(
    [
        {
            "entity_id": get_id(filepath, "make_cats_happy.feed_and_water_cats.feed_cats"),
            "solution_eid": get_id(filepath, "cat_happiness_device.feeding_system.feed_cats"),
            "solution_status": "in progress",
        },
        {
            "entity_id": get_id(filepath, "make_cats_happy.adore_cats"),
            "solution_eid": None,
            "solution_status": None,
        },
    ]
)
