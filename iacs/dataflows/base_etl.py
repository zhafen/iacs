from hamilton.function_modifiers import subdag, source

from .etl import load_manifest, derive_components
from .validation import validate_registry
from ..registry import Registry

@subdag(
    load_manifest,
    inputs={"input_dir": source("input_dir")},
    config={}
)
def loaded_registry(registry: Registry) -> Registry:
    return registry

@subdag(
    validate_registry,
    inputs={"registry": source("loaded_registry")},
   config={}
)
def validated_registry(validated_registry: Registry) -> Registry:
    return validated_registry

@subdag(
    derive_components,
    inputs={"validated_registry": source("validated_registry")},
   config={}
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
