import pandas as pd

from iacs.utils import dhash

filepath = "examples/impact-cost_analysis/manifest.yaml"


def get_id(path):
    return dhash(f"{filepath}:{path}")

resolved_impact_cost = pd.DataFrame([
    {
        "entity_id": get_id("activities.video_games.expedition_33"),
        "impact": (impact0 := (0.75 * 4) + (0.25 * 0.2)),
        # 1 unit of concentration, 40 usd
        "cost": (cost0 := (1 * 2) + (40 * (4 / 50))),
        "diff": impact0 - cost0,
        "ratio": impact0 / cost0,
    },
])
