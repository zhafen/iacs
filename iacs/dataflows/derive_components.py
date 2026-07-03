import ibis
import pandas as pd
from hamilton.function_modifiers import subdag, source

from ..registry import Registry
from .derive import impact_cost, inherit_components, resolve_paths


@subdag(resolve_paths, inputs={"registry": source("registry")}, config={})
def resolved_registry(resolved_registry: Registry) -> Registry:
    return resolved_registry


def stripped_registry(resolved_registry: Registry) -> Registry:
    """Strip leading/trailing whitespace from description-typed fields.

    Strips the ``value`` column of the ``description`` component and any field
    columns in other component tables whose declared type is ``description``.
    """
    components = resolved_registry._components
    updated: dict = {}

    field_df = components["field"].to_pandas() if "field" in components else pd.DataFrame()
    entity_id_df = components["entity_id"].to_pandas() if "entity_id" in components else pd.DataFrame()

    fields_by_comp: dict[str, list[str]] = {}
    if not field_df.empty and not entity_id_df.empty and "type" in field_df.columns:
        desc_fields = field_df[field_df["type"] == "description"]
        id_to_key = entity_id_df.set_index("value")["entity_key"]
        for _, row in desc_fields.iterrows():
            comp_type = id_to_key.get(row["entity_id"])
            if comp_type:
                fields_by_comp.setdefault(comp_type, []).append(row["value"])

    if "description" in components:
        df = components["description"].to_pandas().copy()
        if "value" in df.columns:
            df["value"] = df["value"].apply(lambda v: v.strip() if isinstance(v, str) else v)
            updated["description"] = ibis.memtable(df)

    for comp_type, field_names in fields_by_comp.items():
        if comp_type not in components:
            continue
        df = (updated.get(comp_type) or components[comp_type]).to_pandas().copy()
        for col in field_names:
            if col in df.columns:
                df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
        updated[comp_type] = ibis.memtable(df)

    resolved_registry.update(updated)
    return resolved_registry


@subdag(inherit_components, inputs={"registry": source("stripped_registry")}, config={})
def field_derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry


@subdag(
    impact_cost,
    inputs={"registry": source("field_derived_registry")},
    config={},
)
def derived_registry(derived_registry: Registry) -> Registry:
    return derived_registry
