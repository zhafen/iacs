"""Hamilton DAG for parsing entity-first data from EC file text."""

import yaml


def _find_malformed_entities(entities: dict) -> list[str]:
    # Scan for components given as a bare YAML mapping instead of the required
    # list form. Downstream flattening treats a dict value as a nested-entity
    # container rather than raising, so it silently produces zero rows --
    # this check is the only thing that catches it before it reaches the merge step.
    #
    # A dict value is ambiguous: legitimate nested-entity container, or the mistake.
    # Recurse only while every value is itself a list, dict, or null -- a non-null
    # scalar means this level was meant as a component list.
    # Null is valid: a bare `key:` is a real, componentless placeholder entity
    # (e.g. `required_functionality:` in iacs.yaml) -- treating it as malformed
    # broke real data. "data" is exempt everywhere (EC freeform-notes convention).
    #
    # Returns dotted paths of malformed components, empty if none found.
    malformed: list[str] = []

    def check(path: str, value) -> None:
        if value is None or isinstance(value, list):
            return
        if isinstance(value, dict) and value and all(
            v is None or isinstance(v, (list, dict))
            for k, v in value.items() if k != "data"
        ):
            for key, sub_value in value.items():
                if key != "data":
                    check(f"{path}.{key}", sub_value)
            return
        malformed.append(path)

    for alias, value in entities.items():
        if alias != "data":
            check(alias, value)
    return malformed


def raw_entity_first_data(raw_yaml_strings: dict[str, str]) -> dict:
    """Parse raw YAML text into entity-first dicts, keyed by file identifier.

    Raises if any file's entities include a component given as a bare
    mapping instead of a list -- see `_find_malformed_entities`. A parse
    failure or non-dict top-level shape is left to normal YAML/downstream
    error handling rather than checked here.

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
        parsed = yaml.safe_load(content) or {}
        if isinstance(parsed, dict):
            malformed = _find_malformed_entities(parsed)
            if malformed:
                raise ValueError(
                    "Each entity's components must be a YAML list (a leading `- ` "
                    "before each component name), e.g. `alias:\n    - component:\n"
                    "        value: x` -- a bare mapping (`alias:\n    component:\n"
                    "        value: x`) is silently ignored rather than merged. "
                    f"Malformed in {file_id}: {', '.join(malformed)}."
                )
        result[file_id] = parsed
    return result


FINAL_VAR = "raw_entity_first_data"
