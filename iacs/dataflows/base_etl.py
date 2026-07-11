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


FINAL_VAR = "validated_registry"
