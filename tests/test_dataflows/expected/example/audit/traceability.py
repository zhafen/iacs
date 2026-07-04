import pandas as pd

from iacs.utils import get_id, dhash

example_filepath = "examples/example/manifest.yaml"

traceability = pd.DataFrame(
    [
        # Builtin entities — no requirements, no solution-of
        {"entity_id": dhash("builtins.components:component"),
         "message": "Entity 'dac3bf7914c7' does not trace to any requirement."},
        {"entity_id": dhash("builtins.components:data_structure.field"),
         "message": "Entity 'f40430b19949' does not trace to any requirement."},
        {"entity_id": dhash("builtins.components:iacs_component.entity_id"),
         "message": "Entity 'd8f8762ec947' does not trace to any requirement."},
        # Example manifest entities — no requirements, no solution-of
        {"entity_id": get_id(example_filepath, "cat"),
         "message": "Entity 'e6d81db4e175' does not trace to any requirement."},
        {"entity_id": get_id(example_filepath, "cat_food_supply.furina"),
         "message": "Entity '357bf9ecd1f0' does not trace to any requirement."},
        {"entity_id": get_id(example_filepath, "cat_food_supply_list_format"),
         "message": "Entity 'd9fac45a5dff' does not trace to any requirement."},
    ]
)
