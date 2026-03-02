"""A dataflow for deriving additional components from the base input.
This is intended to be completed post-validation, so fields need to be derived
separately as part of validation.
"""

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry

@extract_fields({
    "spine": ir.Table,
})
def components(registry: Registry) -> dict:
    return registry._components