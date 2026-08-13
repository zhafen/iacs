"""Hamilton DAG for parsing entity-first data from EC file text."""

import yaml


def raw_entity_first_data(raw_yaml_strings: dict[str, str]) -> dict:
    """Parse raw YAML text into entity-first dicts, keyed by file identifier.

    Parameters
    ----------
    raw_yaml_strings : dict[str, str]
        A dict keyed by file identifier, where each value is raw YAML text.

    Returns
    -------
    dict
        A dict keyed by file identifier, where each value is the dict of
        entities loaded from that file's YAML text.
    """
    result = {}
    for file_id, content in raw_yaml_strings.items():
        result[file_id] = yaml.safe_load(content) or {}
    return result


FINAL_VAR = "raw_entity_first_data"
