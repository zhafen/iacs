"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.
"""

import pandas as pd

from iacs.registry import Registry
from iacs.utils import candidate_entity_ids


def field_types_with_entity_ref(validated_registry: Registry) -> dict[str, list[str]]:
    """Return a mapping of component_type -> [field_names] for entity_ref fields.

    Parameters
    ----------
    validated_registry : Registry
        The validated registry.

    Returns
    -------
    dict[str, list[str]]
        E.g. ``{"solution": ["target"]}``
    """
    field_df = validated_registry._components["field"].to_pandas()
    entity_id_df = validated_registry._components["entity_id"].to_pandas()

    entity_ref_fields = field_df[field_df["type"] == "entity_ref"]
    id_to_key = entity_id_df.set_index("value")["entity_key"]

    result: dict[str, list[str]] = {}
    for _, row in entity_ref_fields.iterrows():
        comp_type = id_to_key.get(row["entity_id"])
        if comp_type:
            result.setdefault(comp_type, []).append(row["value"])
    return result


def components_with_resolved_paths(
    validated_registry: Registry,
    field_types_with_entity_ref: dict[str, list[str]],
) -> dict[str, pd.DataFrame]:
    """Resolve entity_ref fields in each component to entity IDs.

    For each (component_type, field_names) pair, adds a ``{field}_id`` column
    containing the resolved entity ID (or ``None`` if 0 or 2+ candidates match).

    Parameters
    ----------
    validated_registry : Registry
        The validated registry.
    field_types_with_entity_ref : dict[str, list[str]]
        Mapping of component_type -> list of field names with entity_ref type.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of component_type -> DataFrame with resolved ``{field}_id`` columns.
    """
    entity_id_df = validated_registry._components["entity_id"].to_pandas()

    result: dict[str, pd.DataFrame] = {}
    for comp_type, field_names in field_types_with_entity_ref.items():
        df = validated_registry._components[comp_type].to_pandas()
        for field_name in field_names:
            if field_name not in df.columns:
                continue

            def resolve(val, _df=entity_id_df):
                if pd.isna(val):
                    return None
                candidates = candidate_entity_ids(str(val), _df)
                return candidates[0] if len(candidates) == 1 else None

            df[f"{field_name}_id"] = df[field_name].apply(resolve)
        result[comp_type] = df
    return result
