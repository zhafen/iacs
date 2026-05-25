import ibis
import ibis.expr.types as ir
import pandera.ibis as pa

from hamilton.function_modifiers import extract_fields, unpack_fields

def validated_components(
    components: dict, field: ir.Table,
) -> ir.Table:
    """Use the schemas defined by the ((field)) component to validate and coerce
    the data in each component.

    Materialise only the schema-defining rows (O(fields) records per component type),
    build ibis mutate chains for column addition, type casting, and default filling,
    then validate types with :mod:`pandera.ibis`.  Constraint violations (nullable,
    categorical range) are collected as ibis filter sub-queries and unioned into
    ``invalid_field`` without pulling component data into memory.

    Parameters
    ----------
    updated_components : dict
        Dict of component_type -> ibis Table (from ``updated_components``).
    derived_field : ir.Table
        Inheritance-resolved field definitions (from ``derived_field``).
    entity_id : ir.Table
        One row per entity (hash, path, value, alias, entity_key, filepath),
        used to map entity_key -> entity_id for schema lookup.

    Returns
    -------
    tuple[dict, ir.Table]
        ``(validated_components, invalid_field)`` where ``validated_components``
        is a dict of component_type -> coerced ibis Table, and ``invalid_field``
        is an ibis Table of rows that failed nullable or range constraints.
    """

    # Loop through and validate
    for component_type, component_table in components.items():

        # Get the relevant fields
        field_per_component = field.select(ibis.Column("entity") == component_type)

        # Assemble the schema
        schema = pa.DataFrameSchema({
            # Get this by looping through field_per_component
        })
        
        # Apply the validation
        schema.validate(component_table).execute()

    return components