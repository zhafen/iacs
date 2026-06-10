"""Conversion between entity-first YAML format and alternate YAML format.

Alternate format rules
----------------------
All entities are represented as dicts.  Within an entity dict each key is
either a component name or a child-entity name, distinguished by value type:

* ``None`` (YAML ``~``) — tag component (presence-only, no value)
* atomic (str, int, float, bool) — scalar component
* list — multiple instances of that component type; each list item is either:
  - a scalar  → single-value instance
  - a dict    → sub-field instance (field names as keys)
* dict — child entity (recursed)

A component with exactly one sub-field instance can be written with a
single-item list:  ``link: [{source: A, target: B}]``.

The current ("classic") entity-first format represents every entity either as
a list of component entries (flat entity) or as a dict whose ``"data"`` key
holds the entity's own components and all other keys are child entities
(nested entity).
"""

from __future__ import annotations

_ATOMIC = (str, int, float, bool)


def _is_atomic(v) -> bool:
    return v is None or isinstance(v, _ATOMIC)


# ---------------------------------------------------------------------------
# entity_first  →  alternate
# ---------------------------------------------------------------------------

def _comp_to_alt(comp) -> tuple[str, object]:
    """Convert one classic component entry to an (alternate_key, alternate_value) pair."""
    if isinstance(comp, str):
        return comp, None                           # tag

    assert isinstance(comp, dict) and len(comp) == 1, f"Unexpected component: {comp!r}"
    key = next(iter(comp))
    val = comp[key]

    if isinstance(val, list):
        # Already a multi-instance list; items are scalars or sub-field dicts.
        return key, val

    if isinstance(val, dict):
        if val and all(isinstance(v, dict) for v in val.values()):
            # Keyed multi-instance: {name1: {f: v}, name2: {f: v}}
            # → list with explicit "value" field per instance
            instances = [{"value": name, **fields} for name, fields in val.items()]
            return key, instances
        else:
            # Single sub-field instance: {f1: v1, f2: v2}
            return key, [val]

    # Scalar (incl. None for tags written as {k: null})
    return key, val


def _merge_alt(result: dict, key: str, val) -> None:
    """Insert (key, val) into result, merging duplicate keys into a list."""
    if key not in result:
        result[key] = val
        return
    existing = result[key]
    # Coerce both sides to list and concatenate
    left = existing if isinstance(existing, list) else [existing]
    right = val if isinstance(val, list) else [val]
    result[key] = left + right


def _flat_entity_to_alt(components: list) -> dict:
    result: dict = {}
    for comp in components:
        k, v = _comp_to_alt(comp)
        _merge_alt(result, k, v)
    return result


def _nested_entity_to_alt(entity_val: dict) -> dict:
    result: dict = {}
    for comp in entity_val.get("data", []):
        k, v = _comp_to_alt(comp)
        _merge_alt(result, k, v)
    for child_key, child_val in entity_val.items():
        if child_key == "data":
            continue
        result[child_key] = _entity_to_alt(child_val)
    return result


def _entity_to_alt(entity_val) -> dict:
    if entity_val is None:
        return {}
    if isinstance(entity_val, list):
        return _flat_entity_to_alt(entity_val)
    if isinstance(entity_val, dict):
        return _nested_entity_to_alt(entity_val)
    return {}


def entity_first_to_alternate(entity_first_data: dict) -> dict:
    """Convert entity-first YAML data to alternate format.

    Parameters
    ----------
    entity_first_data : dict
        ``{entity_key: entity_value}`` in the classic entity-first format.

    Returns
    -------
    dict
        ``{entity_key: entity_dict}`` in alternate format.
    """
    return {k: _entity_to_alt(v) for k, v in entity_first_data.items()}


# ---------------------------------------------------------------------------
# alternate  →  entity_first
# ---------------------------------------------------------------------------

def _alt_entry_to_comps(key: str, val) -> list:
    """Convert one alternate key-value entry to a list of classic component entries."""
    if val is None:
        return [key]                                # tag

    if _is_atomic(val):
        return [{key: val}]                         # scalar

    if isinstance(val, list):
        if len(val) == 1:
            item = val[0]
            # Single-item list: unwrap to scalar or sub-field dict
            return [{key: item}]
        # Multi-instance: keep as {key: [item, ...]}
        return [{key: val}]

    # Should not reach here for dict (caller handles child entities separately).
    raise TypeError(f"Unexpected value type for key {key!r}: {type(val)}")


def _alt_entity_to_classic(alt_dict: dict):
    """Convert one alternate entity dict to a classic entity_first value.

    Returns a list (flat entity) or dict with optional ``"data"`` key
    (nested entity).
    """
    if not alt_dict:
        return []

    components: list = []
    children: dict = {}

    for key, val in alt_dict.items():
        if isinstance(val, dict):
            children[key] = _alt_entity_to_classic(val)
        else:
            components.extend(_alt_entry_to_comps(key, val))

    if not children:
        return components
    if not components:
        return {ck: cv for ck, cv in children.items()}
    return {"data": components, **{ck: cv for ck, cv in children.items()}}


def alternate_to_entity_first(alternate_data: dict) -> dict:
    """Convert alternate-format entity data back to classic entity-first format.

    Parameters
    ----------
    alternate_data : dict
        ``{entity_key: entity_dict}`` in alternate format.

    Returns
    -------
    dict
        ``{entity_key: entity_value}`` in classic entity-first format.
    """
    return {k: _alt_entity_to_classic(v) for k, v in alternate_data.items()}
