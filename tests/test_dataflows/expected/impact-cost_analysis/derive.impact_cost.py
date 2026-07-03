import pandas as pd

from iacs.utils import dhash

filepath = "examples/impact-cost/manifest.yaml"


def get_id(path):
    return dhash(f"{filepath}:{path}")

resolved_impact_cost = pd.DataFrame([
    {
        "entity_id": get_id("activities.side_projects.work_on_iacs"),
        "impact": (0.25 * 4) + (0.5 * 0.2) + (0.25 * 1) + (1 * 1.5),
    },
])
