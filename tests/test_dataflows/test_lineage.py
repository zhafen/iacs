"""Tests for the lineage utilities in iacs.dataflows.etl.derive_components."""

import iacs.dataflows.etl.derive_components as derive_components
from iacs.dataflows.etl.derive_components import derived_component_types


def test_derived_component_types_returns_expected():
    result = derived_component_types(derive_components)
    assert set(result) == {"entity_depth", "effort_total", "priority_product"}


def test_derived_component_types_excludes_registry_and_dict_params():
    result = derived_component_types(derive_components)
    assert "validated_registry" not in result
    assert "components_with_resolved_paths" not in result


def test_derived_component_types_returns_list():
    result = derived_component_types(derive_components)
    assert isinstance(result, list)


def test_derived_component_types_no_derived_registry_returns_empty():
    import types
    empty_module = types.ModuleType("empty")
    assert derived_component_types(empty_module) == []
