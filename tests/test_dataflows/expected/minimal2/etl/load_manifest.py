import pandas as pd

raw_entity_first_data = {
    "examples/minimal2/minimal2.yaml": {
        # Deliberately expressed as a plain list of "core_requirement"'s own
        # components (no children) even though the entity has children in the
        # actual data (which nests the entity's own components under a "data"
        # key alongside the child entities). This exercises the "data"-unwrap
        # branch in _assert_manifest_subset: tests/test_human_validated.py.
        "core_requirement": [
            {"description": "The main requirement the infrastructure must complete."},
            "requirement",
        ],
        "my_infrastructure": [
            {"description": "The overall infrastructure used to complete the core requirement."},
        ],
    },
}

# A dict expected_value compared against the Registry actual value returned by
# the "registry" node, exercising the Registry branch in _assert_subset:
# tests/test_human_validated.py.
registry = {
    "description.value": pd.DataFrame(
        [
            {"description.value": "The main requirement the infrastructure must complete."},
        ]
    ),
}
