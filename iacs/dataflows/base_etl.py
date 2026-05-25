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


def field_types_with_entity_ref(entity_id: ir.Table, field: ir.Table) -> dict[str, list[str]]:
    from .derive.resolve_paths import field_types_with_entity_ref as _ftwer
    return _ftwer(entity_id, field)


def components_with_resolved_paths(
    entity_id: ir.Table,
    loaded_components: dict,
    field_types_with_entity_ref: dict[str, list[str]],
) -> dict:
    from .derive.resolve_paths import components_with_resolved_paths as _cwrp
    return _cwrp(
        entity_id=entity_id,
        components=loaded_components,
        field_types_with_entity_ref=field_types_with_entity_ref,
    )


_INFRA_TYPES = frozenset({"entity_id", "component_type", "invalid_field", "schema"})


def validated_registry(
    loaded_components: dict,
    field: ir.Table,
    entity_id: ir.Table,
    updated_parent: ir.Table,
    loaded_registry: Registry,
    components_with_resolved_paths: dict,
) -> Registry:
    from .validation.validate_components import validated_components as _run_validation
    user_comps = {k: v for k, v in loaded_components.items() if k not in _INFRA_TYPES}
    validated_comps, invalid_table = _run_validation(user_comps, field, entity_id)
    loaded_registry.update({
        **validated_comps,
        "invalid_field": invalid_table,
        "parent": updated_parent,
    })
    return loaded_registry


def registry(validated_registry: Registry) -> Registry:
    """Expose the validated registry as 'registry' for downstream modules."""
    return validated_registry


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
