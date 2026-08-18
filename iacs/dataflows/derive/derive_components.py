"""iacs's own derive pipeline: emc2p's generic derive_components, extended
with impact/cost scoring (see ``impact_cost``).
"""
from hamilton.function_modifiers import subdag, source

from emc2p.registry import Registry
import emc2p.dataflows.derive.derive_components as _base_derive_components
from . import impact_cost


@subdag(_base_derive_components, inputs={"registry": source("registry")}, config={})
def base_derived_registry(time_filled_registry: Registry) -> Registry:
    return time_filled_registry


@subdag(
    impact_cost,
    inputs={"registry": source("base_derived_registry")},
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry


FINAL_VAR = "derived_registry"
