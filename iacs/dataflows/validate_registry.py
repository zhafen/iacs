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


def parent_from_path(spine: ir.Table) -> ir.Table:
    """Convert the paths in the spine into parent-child relationships.

    Parameters
    ----------
    spine : ir.Table

    Returns
    -------
    ir.Table
    """

    return


def updated_parent(parent: ir.Table, parent_from_path: ir.Table) -> ir.Table:

    return


def updated_registry(updated_parent: ir.Table) -> Registry:

    return
