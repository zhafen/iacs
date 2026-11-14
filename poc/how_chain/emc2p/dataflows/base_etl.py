"""Chains the etl, derive, and validation subdags into the one pipeline that produces a validated_registry.

Components
----------
- how:
      - value: base_etl.loaded_registry
        question: "How is `loaded_registry` implemented?"
      - value: base_etl.initial_validated_registry
        question: "How is `initial_validated_registry` implemented?"
      - value: base_etl.derived_registry
        question: "How is `derived_registry` implemented?"
      - value: base_etl.validated_registry
        question: "How is `validated_registry` implemented?"
"""

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
