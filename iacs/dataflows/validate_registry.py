"""This module validates the data in the registry against their schema and coerces or
warns as appropriate.
"""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ..registry import Registry


@extract_fields(dict(spine=ir.Table, parent=ir.Table, field=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in a registry."""

    return registry._components


def updated_parent(spine: ir.Table, parent: ir.Table) -> ir.Table:
    """Convert the paths in the spine into parent-child relationships and
    add them to the parent component.

    Parameters
    ----------
    spine : ir.Table

    Returns
    -------
    ir.Table
    """

    return


def validated_field(field: ir.Table) -> ir.Table:
    """The ((field)) component contains the data for the schema for all components.
    This includes the ((field)) component itself. We will use the ((field)) component
    to validate the data in all components, but first we need to use the appropriate
    records in the ((field)) component to validate the data in just the ((field))
    component.

    Parameters
    ----------
    field : ir.Table
        _description_

    Returns
    -------
    ir.Table
        _description_
    """

    return


def derived_field(validated_field: ir.Table, updated_parent: ir.Table) -> ir.Table:
    """Component definitions inherit fields from their parents, but can override them.
    The derived_field table contains the results of applying this inheritance.

    Parameters
    ----------
    validated_field : ir.Table
        _description_
    updated_parent : ir.Table
        _description_

    Returns
    -------
    ir.Table
        _description_
    """

    return


def updated_components(
    updated_parent: ir.Table, derived_field: ir.Table, registry: Registry
) -> dict:
    """Store the components updated so far back in the registry.

    Parameters
    ----------
    updated_parent : ir.Table
        _description_
    derived_field : ir.Table
        _description_

    Returns
    -------
    Registry
        _description_
    """

    return

def validated_components(updated_components: dict, derived_field: ir.Table) -> dict:
    """Use the schemas defined by the ((field)) component to validate and coerce the data in each component.

    Parameters
    ----------
    updated_components : dict
        _description_
    derived_field : _type_
        _description_

    Returns
    -------
    dict
        _description_
    """

    return

def validated_registry(validated_components: dict, registry: Registry) -> Registry:
    """Store the components back in the registry.

    Parameters
    ----------
    validated_components : dict
        _description_
    registry : Registry
        _description_

    Returns
    -------
    Registry
        _description_
    """

    return
