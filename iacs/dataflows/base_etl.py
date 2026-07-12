from hamilton.function_modifiers import subdag, source

import iacs.dataflows.derive.derive_components as _derive_components
import iacs.dataflows.validation.validate_components as _validate_components
from .etl import load_manifest
from ..registry import Registry


@subdag(load_manifest, inputs={"input_dirs": source("input_dirs")}, config={})
def loaded_registry(registry: Registry) -> Registry:
    return registry


@subdag(
    _validate_components,
    inputs={"registry": source("loaded_registry")},
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


@subdag(
    _validate_components,
    inputs={"registry": source("derived_registry")},
    config={},
)
def validated_registry(validated_registry: Registry) -> Registry:
    return validated_registry


FINAL_VAR = "validated_registry"
