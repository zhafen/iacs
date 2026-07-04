import pandas as pd

from iacs.utils import get_id

filepath = "examples/example/manifest.yaml"

def _eid(path):
    return get_id(filepath, path)

_hierarchical_file_str = """
make_cats_happy:
    data:
        - description: The mission of our cat-happiness device.
        - requirement:
            value: 1.0
            type: functional
    feed_and_water_cats:
        - description: Obviously.
        - requirement:
            value: 1.0
            type: functional
"""

# entity_first_data is now keyed by entity_id
entity_first_data = {
    _eid("make_cats_happy"): [
        (0, {"description": {"value": "The mission of our cat-happiness device."}}),
        (1, {"requirement": {"value": 1.0, "type": "functional"}}),
    ],
    _eid("make_cats_happy.feed_and_water_cats"): [
        (0, {"description": {"value": "Obviously."}}),
        (1, {"requirement": {"value": 1.0, "type": "functional"}}),
    ],
}

condensed_entity_first_data = {
    _eid("make_cats_happy"): [
        (0, {"description": "The mission of our cat-happiness device."}),
        (1, {"requirement": {"value": 1.0, "type": "functional"}}),
    ],
    _eid("make_cats_happy.feed_and_water_cats"): [
        (0, {"description": "Obviously."}),
        (1, {"requirement": {"value": 1.0, "type": "functional"}}),
    ],
}

# filepath-keyed format is NOT the format of entity_first_data any more
incorrect_entity_first_data = {
    filepath: {"make_cats_happy": []}
}

import yaml
hierarchical_entity_first_data = {
    filepath: yaml.safe_load(_hierarchical_file_str)
}
