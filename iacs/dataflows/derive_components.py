from hamilton.function_modifiers import subdag, source

from ..registry import Registry
from .derive import calculate_effort_and_priority, inherit_components, resolve_paths


@subdag(resolve_paths, inputs={"registry": source("registry")}, config={})
def resolved_registry(resolved_registry: Registry) -> Registry:
    return resolved_registry


@subdag(inherit_components, inputs={"registry": source("resolved_registry")}, config={})
def field_derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry


def components_with_resolved_paths(resolved_registry: Registry) -> dict:
    """Re-expose resolved component tables for calculate_effort_and_priority."""
    return {
        k: v
        for k, v in resolved_registry._components.items()
        if hasattr(v, "columns") and any(c.endswith("_eid") for c in v.columns)
    }


@subdag(
    calculate_effort_and_priority,
    inputs={
        "validated_registry": source("field_derived_registry"),
        "components_with_resolved_paths": source("components_with_resolved_paths"),
    },
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
