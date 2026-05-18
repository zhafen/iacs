import yaml

_flat_file_str = (
"""
make_cats_happy:
    - description:
        value: The mission of our cat-happiness device.
    - requirement:
        value: 1.0
        type: functional
feed_and_water_cats:
    - description:
        value: Obviously.
    - requirement:
        value: 1.0
        type: functional
"""
)
_hierarchical_file_str = (
"""
make_cats_happy:
    data:
        - description:
            value: The mission of our cat-happiness device.
        - requirement:
            value: functional
            priority: 1
    feed_and_water_cats:
        - description:
            value: Obviously.
        - requirement:
            value: functional
            priority: 1
"""
)
entity_first_data = {
    "examples/example/manifest.yaml": yaml.safe_load(_flat_file_str)
}
# This should NOT work.
incorrect_entity_first_data = {
    "examples/example/manifest.yaml": yaml.safe_load(_hierarchical_file_str)
}