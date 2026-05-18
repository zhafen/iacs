"""Utilities for deriving component lineage from Hamilton DAGs."""

import inspect
import pandas as pd
from typing import get_type_hints
from types import ModuleType


def derived_component_types(module: ModuleType) -> list[str]:
    """Return component type names that are purely derived in a Hamilton module.

    Inspects the ``derived_registry`` function's parameters and returns the names
    of those whose producer functions (in the same module) return ``pd.DataFrame``.
    These are component types added to the registry as new tables by the derivation
    step, not components sourced directly from YAML.

    Parameters
    ----------
    module : ModuleType
        A Hamilton DAG module, typically ``iacs.dataflows.etl.derive_components``.

    Returns
    -------
    list[str]
        Component type names (e.g. ``["entity_depth", "effort_total", "priority_product"]``).
    """
    derived_registry_fn = getattr(module, "derived_registry", None)
    if derived_registry_fn is None:
        return []

    sig = inspect.signature(derived_registry_fn)
    result = []
    for param_name in sig.parameters:
        if param_name in ("validated_registry", "components_with_resolved_paths"):
            continue
        producer_fn = getattr(module, param_name, None)
        if producer_fn is None:
            continue
        try:
            hints = get_type_hints(producer_fn)
        except Exception:
            continue
        if hints.get("return") is pd.DataFrame:
            result.append(param_name)
    return result
