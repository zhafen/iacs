from hamilton.function_modifiers import subdag, source

from iacs.registry import Registry
from . import resolve_entity_refs, resolve_hierarchy, estimate_priority

@subdag(
    resolve_entity_refs,
    inputs={"input_dir": source("input_dir")},
    config={}
)
def resolved_registry(registry: Registry) -> Registry:
    return registry

@subdag(
    resolve_hierarchy,
    inputs={"resolved_registry": source("resolved_registry")},
   config={}
)
def hiearchy_resolved_registry(resolved_registry: Registry) -> Registry:
    return resolved_registry

@subdag(
    estimate_priority,
    inputs={"hierarchy_resolved_registry": source("hierarchy_resolved_registry")},
   config={}
)
def efforted_registry(hierarchy_resolved_registry: Registry) -> Registry:
    return hierarchy_resolved_registry