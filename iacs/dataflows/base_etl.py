from typing import Any

import ibis
import ibis.expr.types as ir
from hamilton.function_modifiers import subdag, source

import iacs.dataflows.derive.derive_components as _derive_components
import iacs.dataflows.validation.validate_components as _validate_components
from .etl import load_manifest
from ..registry import Registry


@subdag(load_manifest, inputs={"input_dirs": source("input_dirs")}, config={})
def loaded_registry(registry: Registry) -> Registry:
    return registry


def builtin_field(loaded_registry: Registry) -> ir.Table:
    """Field table limited to schemas defined in the built-in components file.

    At load time the full derived field schema is not yet available.  Using only
    the built-in schemas (not user-defined extensions) avoids false positives on
    fields that only exist after derivation while still typing and defaulting the
    built-in component fields (effort.unit, priority.value, etc.) so the derive
    step has properly-typed data.
    """
    comps = loaded_registry._components
    f = comps["field"]
    eid = comps["entity_id"]
    builtin_eids = eid.filter(eid["filepath"] == "builtins.components").select("value")
    return f.filter(f["entity_id"].isin(builtin_eids["value"]))


@subdag(
    _validate_components,
    inputs={"registry": source("loaded_registry"), "field": source("builtin_field")},
    config={},
)
def initial_validated_registry(validated_registry: Registry) -> Registry:
    return validated_registry


@subdag(
    _derive_components,
    inputs={"registry": source("initial_validated_registry")},
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry


def derived_field(derived_registry: Registry) -> ir.Table:
    """Full field table from the derived registry, including inherited field definitions."""
    return derived_registry._components["field"]


@subdag(
    _validate_components,
    inputs={"registry": source("derived_registry"), "field": source("derived_field")},
    config={},
)
def validated_registry(validated_registry: Registry) -> Registry:
    return validated_registry


def time_filled_registry(validated_registry: Registry, load_time: Any = None) -> Registry:
    """Backfill null time_dimension fields on newly loaded components with ``load_time``.

    Used when loading a manifest that represents a snapshot as of a known
    point in time: the field flagged ``time_dimension: true`` in a component
    type's schema (see ``Registry._time_dimension_field``) is set to
    ``load_time`` wherever it is still null. Values that are already set are
    left untouched. A no-op when ``load_time`` is not given.

    Args:
        validated_registry: The fully derived and validated registry.
        load_time: The point in time this load represents, e.g. a timestamp
            or date string.
    """
    if load_time is None:
        return validated_registry

    updated = {}
    for comp_type in validated_registry.component_types:
        field = validated_registry._time_dimension_field(comp_type)
        table = validated_registry.get(comp_type)
        if field is None or field not in table.columns:
            continue

        df = table.execute()
        if df[field].isna().any():
            df[field] = df[field].fillna(load_time)
            updated[comp_type] = ibis.memtable(df)

    if updated:
        validated_registry.update(updated)

    return validated_registry


def registry(time_filled_registry: Registry) -> Registry:
    """Expose the fully derived and validated registry for downstream modules."""
    return time_filled_registry


FINAL_VAR = "registry"
