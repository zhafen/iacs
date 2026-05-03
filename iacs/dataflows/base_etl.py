from hamilton.function_modifiers import subdag, source

from . import load_manifest, validate_registry, derive_components
from .audit import traceability as audit_traceability, todo as audit_todo
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

@subdag(
    audit_traceability,
    inputs={"registry": source("derived_registry")},
    config={}
)
def traceability_registry(updated_registry: Registry) -> Registry:
    return updated_registry

@subdag(
    audit_todo,
    inputs={"registry": source("traceability_registry")},
    config={}
)
def todo_registry(updated_registry: Registry) -> Registry:
    return updated_registry
