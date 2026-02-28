"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields, unpack_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry

@extract_fields({
    "requirement": ir.Table
})
def components(registry: Registry) -> dict:
    return
