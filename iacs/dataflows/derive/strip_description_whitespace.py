import pandas as pd
import ibis
import ibis.expr.types as ir
from hamilton.function_modifiers import extract_fields

from ...registry import Registry


@extract_fields(dict(field=ir.Table, entity_id=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in the registry."""
    return registry._components


def fields_of_type_description(field: ir.Table, entity_id: ir.Table) -> dict[str, list[str]]:
    """Return a mapping of component_type -> [field_names] for description-typed fields."""
    field_df = field.to_pandas()
    entity_id_df = entity_id.to_pandas()

    description_fields = field_df[field_df["type"] == "description"]
    id_to_key = entity_id_df.set_index("value")["entity_key"]

    result: dict[str, list[str]] = {}
    for _, row in description_fields.iterrows():
        comp_type = id_to_key.get(row["entity_id"])
        if comp_type:
            result.setdefault(comp_type, []).append(row["value"])
    return result


def stripped_registry(
    registry: Registry,
    fields_of_type_description: dict[str, list[str]],
) -> Registry:
    """Strip leading/trailing whitespace from description-typed fields.

    Strips the ``value`` column of the ``description`` component table and any
    field columns in other component tables whose declared type is ``description``.
    """
    components_dict = dict(registry._components)
    updated: dict = {}

    # Always strip the description component's own value column.
    if "description" in components_dict:
        df = components_dict["description"].to_pandas()
        if "value" in df.columns:
            df = df.copy()
            df["value"] = df["value"].apply(
                lambda v: v.strip() if isinstance(v, str) else v
            )
            updated["description"] = ibis.memtable(df)

    # Strip any field columns in other components declared as type description.
    for comp_type, field_names in fields_of_type_description.items():
        if comp_type not in components_dict:
            continue
        df = (updated.get(comp_type) or components_dict[comp_type]).to_pandas()
        df = df.copy()
        for col in field_names:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v: v.strip() if isinstance(v, str) else v
                )
        updated[comp_type] = ibis.memtable(df)

    registry.update(updated)
    return registry
