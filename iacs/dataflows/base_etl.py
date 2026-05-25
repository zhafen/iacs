from hamilton.function_modifiers import subdag, source, extract_fields
import ibis.expr.types as ir

import iacs.dataflows.derive_components as _derive_components
from .etl import load_manifest
from ..registry import Registry


_INFRA_TYPES = frozenset({"entity_id", "component_type", "invalid_field", "schema", "parent", "field"})


@subdag(
    load_manifest,
    inputs={"input_dir": source("input_dir")},
    config={}
)
def loaded_registry(registry: Registry) -> Registry:
    return registry


@extract_fields({"field": ir.Table, "entity_id": ir.Table})
def loaded_components(loaded_registry: Registry) -> dict:
    return loaded_registry._components


def validated_registry(
    loaded_components: dict,
    field: ir.Table,
    entity_id: ir.Table,
    loaded_registry: Registry,
) -> Registry:
    from .validation.validate_components import validated_components as _run_validation
    user_comps = {k: v for k, v in loaded_components.items() if k not in _INFRA_TYPES}
    validated_comps, invalid_table = _run_validation(user_comps, field, entity_id)
    loaded_registry.update({**validated_comps, "invalid_field": invalid_table})
    return loaded_registry


def registry(derived_registry: Registry) -> Registry:
    """Expose the fully derived registry for downstream modules."""
    return derived_registry


@subdag(
    _derive_components,
    inputs={"registry": source("validated_registry")},
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
