import networkx as nx
import pandas as pd
from hamilton.function_modifiers import extract_fields
import ibis.expr.types as ir

from iacs.registry import Registry
from iacs.utils import candidate_entity_ids

@extract_fields(dict(entity_id=ir.Table, field=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in the validated registry."""
    return registry._components


def fields_with_entity_ref(entity_id: ir.Table, field: ir.Table) -> dict[str, list[str]]:
    """Return a mapping of component_type -> [field_names] for entity_ref fields.

    Parameters
    ----------
    field : ir.Table
        The field component table from the registry.
    entity_id : ir.Table
        The entity_id component table from the registry.

    Returns
    -------
    dict[str, list[str]]
        E.g. ``{"solution": ["target"]}``
    """
    field_df = field.to_pandas()
    entity_id_df = entity_id.to_pandas()

    entity_ref_fields = field_df[field_df["type"] == "entity_ref"]
    id_to_key = entity_id_df.set_index("value")["entity_key"]

    result: dict[str, list[str]] = {}
    for _, row in entity_ref_fields.iterrows():
        comp_type = id_to_key.get(row["entity_id"])
        if comp_type:
            result.setdefault(comp_type, []).append(row["value"])
    return result

@extract_fields(dict(resolved_parent=ir.Table))
def resolved_components(
    entity_id: ir.Table,
    components: dict,
    fields_with_entity_ref: dict[str, list[str]],
) -> dict[str, pd.DataFrame]:
    """Resolve entity_ref fields in each component to entity IDs.

    For each (component_type, field_names) pair, adds a ``{field}_eid`` column
    containing the resolved entity ID (or ``None`` if 0 or 2+ candidates match).

    Parameters
    ----------
    entity_id : ir.Table
        The entity_id component table from the registry.
    components : dict
        The full components dict from the registry.
    fields_with_entity_ref : dict[str, list[str]]
        Mapping of component_type -> list of field names with entity_ref type.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of component_type -> DataFrame with resolved ``{field}_id`` columns.
    """
    entity_id_df = entity_id.to_pandas()

    result: dict[str, pd.DataFrame] = {}
    for comp_type, field_names in fields_with_entity_ref.items():
        if comp_type not in components:
            continue
        df = components[comp_type].to_pandas()
        for field_name in field_names:
            if field_name not in df.columns:
                continue

            def resolve(val, _df=entity_id_df):
                if pd.isna(val):
                    return None
                candidates = candidate_entity_ids(str(val), _df)
                return candidates[0] if len(candidates) == 1 else None

            df[f"{field_name}_eid"] = df[field_name].apply(resolve).astype("string")
        result[comp_type] = df
    return result

def resolved_registry(resolved_components: dict) -> Registry:
    return