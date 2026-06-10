from hamilton.function_modifiers import subdag, source

from ..registry import Registry
from .derive import calculate_effort_and_priority, inherit_components, resolve_paths, strip_description_whitespace


@subdag(resolve_paths, inputs={"registry": source("registry")}, config={})
def resolved_registry(resolved_registry: Registry) -> Registry:
    return resolved_registry


@subdag(
    strip_description_whitespace,
    inputs={"registry": source("resolved_registry")},
    config={},
)
def stripped_registry(stripped_registry: Registry) -> Registry:
    return stripped_registry


@subdag(inherit_components, inputs={"registry": source("stripped_registry")}, config={})
def field_derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry


@subdag(
    calculate_effort_and_priority,
    inputs={"registry": source("field_derived_registry")},
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
