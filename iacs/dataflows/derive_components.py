"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.


Right now this file is being used to track transforms that need to be applied
to any arbitrary component for the component to be valid.
"""

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry


def global_paths(paths: ir.Column, component_type_table: ir.Table) -> ir.Column:
    """Check for relative paths and convert them to global paths.
    This is done

    Parameters
    ----------
    paths : ir.Column
        _description_
    component_type_table : ir.Table
        _description_

    Returns
    -------
    ir.Column
        _description_
    """
    return


def resolved_paths(paths: ir.Column, component_type_table: ir.Table) -> ir.Column:
    """Convert a column of paths into a column of entity_ids.

    Parameters
    ----------
    paths : ir.Column
        _description_
    component_type_table : ir.Table
        _description_

    Returns
    -------
    ir.Column
        _description_
    """
    return


def modified_component(component: ir.Table, component_type_table: ir.Table) -> ir.Table:
    """Apply the modifiers listed in component_type_table to the component.
    Possible modifiers as of writing:
    - of: Switches target and source.

    Parameters
    ----------
    component : ir.Table
        _description_
    component_type_table : ir.Table
        _description_

    Returns
    -------
    ir.Table
        _description_
    """
    return