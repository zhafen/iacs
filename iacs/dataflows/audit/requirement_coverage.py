"""Hamilton DAG for the requirement coverage audit."""

from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from emc2p.registry import Registry


INPUT_COMPONENT_TYPES = ["requirement_priority", "solution", "requirement", "status"]


@extract_fields({ct: ir.Table for ct in INPUT_COMPONENT_TYPES})
def components(registry: Registry) -> dict:
    """Give access to the components needed by this dataflow."""
    return {ct: registry.get(ct) for ct in INPUT_COMPONENT_TYPES}


def solution_with_state(solution: ir.Table, status: ir.Table) -> ir.Table:
    """Join solutions with their resolved requirement entity IDs and work state.

    solution.value_eid is populated by derive_components based on the entity_ref
    field declared for the solution component in builtins/components.yaml.
    """
    if "value_eid" not in solution.columns:
        return ibis.memtable(
            [],
            schema={"solution_eid": "string", "entity_id": "string", "solution_status": "string"},
        )
    status_for_join = status.rename({"status_eid": "entity_id", "solution_status": "value"})
    return (
        solution
        .left_join(status_for_join, solution.entity_id == status_for_join.status_eid)
        .select(
            ibis._.entity_id.name("solution_eid"),
            ibis._.value_eid.name("entity_id"),
            ibis._.solution_status,
        )
    )


def requirement_entities(
    requirement_priority: ir.Table, solution: ir.Table, requirement: ir.Table
) -> ir.Table:
    """Entities that count as a requirement.

    Union of several independent ways an entity earns that status, matching
    the conventions documented on the ``requirement``/``solution`` component
    types in emc2p's builtins/auditing.yaml:

    - Tagged: it carries a ``requirement_priority`` component (scored).
    - Solved: it's the target (``value_eid``) of a ``solution`` relation --
      some other entity solves it -- with no tag of its own.
    - Related: it's either side of a ``requirement`` component (the
      directed_relation inverse of ``solution``) -- the thing required
      (``entity_id``) or the thing requiring it (``value_eid``). Without
      this, an entity identified only through ``requirement of`` (e.g.
      null_value_representation in iacs.yaml) never shows up here at all.
    """
    tagged = requirement_priority.select("entity_id").distinct()

    relation_ids = []
    if "value_eid" in solution.columns:
        relation_ids.append(
            solution.filter(ibis._.value_eid.notnull()).select(ibis._.value_eid.name("entity_id"))
        )
    if "value_eid" in requirement.columns:
        relation_ids.append(
            requirement.filter(ibis._.value_eid.notnull()).select(ibis._.value_eid.name("entity_id"))
        )
        relation_ids.append(
            requirement.filter(ibis._.entity_id.notnull()).select("entity_id")
        )

    related = tagged
    for rel in relation_ids:
        related = related.union(rel.distinct())
    return related.distinct()


def requirement_coverage(requirement_entities: ir.Table, solution_with_state: ir.Table) -> ir.Table:
    """For each requirement, show which solution covers it and its status."""
    req = requirement_entities
    return req.left_join(solution_with_state, "entity_id").select(
        ibis._.entity_id,
        ibis._.solution_eid,
        ibis._.solution_status,
    )


def updated_registry(registry: Registry, requirement_coverage: ir.Table) -> Registry:
    """Store the requirement coverage audit result as a component in the registry."""
    registry.update({"requirement_coverage": requirement_coverage})
    return registry


FINAL_VAR = "requirement_coverage"
