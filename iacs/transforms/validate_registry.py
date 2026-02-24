"""This module validates the data in the registry against their schema and coerces or
warns as appropriate.
"""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from ..registry import Registry

@extract_fields(dict(path=ir.Table, parent=ir.Table))
def components(registry: Registry):
    """Give access to the components in a registry."""

    return registry._components

def hierarchy(spine: ir.Table) -> ir.Table:
    """Convert the paths in the spine into parent-child relationships.

    Parameters
    ----------
    spine : ir.Table

    Returns
    -------
    ir.Table
    """

    return

def updated_parent(parent: ir.Table, hierarchy: ir.Table) -> ir.Table:

    return