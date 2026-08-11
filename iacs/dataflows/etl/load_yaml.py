"""Hamilton DAG for parsing entity-first data from EC file text."""

import yaml


def _find_malformed_entities(entities: dict) -> list[str]:
    """Scan a parsed entity-first dict for components given as a bare YAML
    mapping instead of the required list form (`alias:\\n    component:\\n
    value: x` instead of `alias:\\n    - component:\\n        value: x`).

    Downstream flattening (`load_manifest._flatten_to_pathvalue` /
    `_collect_entity_paths`) treats any dict value as a nested-entity
    container: an optional `data` key holds the entity's own component list,
    every other key names a child entity, and a bare `null` value (a key
    with nothing after the colon) is a valid, componentless placeholder
    entity -- e.g. `iacs_manifest/iacs.yaml`'s `required_functionality:`
    block, which stubs out `load_data:`/`coerce:`/etc. as not-yet-fleshed-out
    entity names ahead of giving them real components. A bare mapping meant
    as a component list looks exactly like a legitimate container up until
    its innermost values turn out to be plain non-null scalars rather than
    further lists/dicts/nulls -- at that point nothing downstream raises, it
    just produces zero rows for that path, so the write silently does
    nothing.

    A dict value is ambiguous on its own: it's either a malformed component
    list (the mistake above) or a legitimate nested-entity dict (each key
    its own child entity, some possibly still null placeholders).
    Distinguished here by recursing only when *every* value at this level is
    itself a list, dict, or null -- a bare non-null scalar anywhere means
    this level was meant as a component list, not further nesting. `"data"`
    is skipped everywhere, matching EC's own freeform-notes convention
    (never itself a component list).

    Parameters
    ----------
    entities : dict
        A parsed entity-first dict, as returned per-file by
        `raw_entity_first_data`.

    Returns
    -------
    list[str]
        Dotted paths (relative to this dict) of malformed components, empty
        if none found.
    """
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
