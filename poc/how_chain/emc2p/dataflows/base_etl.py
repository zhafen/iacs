"""Chains the etl, derive, and validation subdags into the one pipeline that produces a validated_registry."""

from hamilton.function_modifiers import subdag, source

import emc2p.dataflows.derive.derive_components as _derive_components
import emc2p.dataflows.validation.validate_components as _validate_components
from .etl import load_manifest
from ..registry import Registry


@subdag(load_manifest, inputs={"input_dirs": source("input_dirs")}, config={})
def loaded_registry(registry: Registry) -> Registry:
    """Run the etl subdag's load_manifest and surface its registry."""
    return registry


@subdag(
    _validate_components,
    inputs={"registry": source("loaded_registry")},
    config={},
)
def initial_validated_registry(validated_registry: Registry) -> Registry:
    """Validate the freshly-loaded registry before anything gets derived from it."""
    return validated_registry


@subdag(
    _derive_components,
    inputs={"registry": source("initial_validated_registry")},
    config={},
)
def derived_registry(time_filled_registry: Registry) -> Registry:
    """Run the derive subdag over the validated registry and surface its result."""
    return time_filled_registry


@subdag(
    _validate_components,
    inputs={"registry": source("derived_registry")},
    config={},
)
def validated_registry(validated_registry: Registry) -> Registry:
    """Validate the derived registry one last time; the pipeline's final output."""
    return validated_registry


FINAL_VAR = "validated_registry"
