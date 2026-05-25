from hamilton.function_modifiers import subdag, source, extract_fields
import ibis.expr.types as ir

from .derive import calculate_effort_and_priority
from .etl import load_manifest
from ..registry import Registry


@subdag(
    load_manifest,
    inputs={"input_dir": source("input_dir")},
    config={}
)
def loaded_registry(registry: Registry) -> Registry:
    return registry


@extract_fields({"field": ir.Table, "entity_id": ir.Table, "parent": ir.Table})
def loaded_components(loaded_registry: Registry) -> dict:
    return loaded_registry._components


def parent_from_hierarchy(entity_id: ir.Table) -> ir.Table:
    from .derive.resolve_paths import parent_from_hierarchy as _pfh
    return _pfh(entity_id)


def updated_parent(
    entity_id: ir.Table, parent: ir.Table, parent_from_hierarchy: ir.Table
) -> ir.Table:
    from .derive.resolve_paths import updated_parent as _up
    return _up(entity_id, parent, parent_from_hierarchy)


def validated_registry(
    loaded_components: dict,
    field: ir.Table,
    entity_id: ir.Table,
    updated_parent: ir.Table,
    loaded_registry: Registry,
) -> Registry:
    from .validation.validate_components import validated_components as _run_validation
    validated_comps, invalid_table = _run_validation(loaded_components, field, entity_id)
    new_components = {
        **loaded_registry._components,
        **validated_comps,
        "invalid_field": invalid_table,
        "parent": updated_parent,
    }
    return Registry(loaded_registry._con, new_components)


def components_with_resolved_paths(validated_registry: Registry) -> dict:
    """Placeholder: entity-ref path resolution is not wired in this pipeline."""
    return {}


@subdag(
    calculate_effort_and_priority,
    inputs={
        "validated_registry": source("validated_registry"),
        "components_with_resolved_paths": source("components_with_resolved_paths"),
    },
    config={}
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
