import yaml

_file_str = """make_cats_happy:
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

raw_entity_first_data = yaml.safe_load(_file_str)

exported_manifest_filepaths = [
    "../test_data/temp/example/manifest.yaml"
]
