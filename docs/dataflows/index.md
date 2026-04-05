# Dataflow DAGs

Hamilton DAG visualizations for all iacs dataflows.
Regenerate images with: `uv run python docs/gen_dag_images.py`

---

## load_manifest

Converts entity-centered YAML data into the component-centered Registry format.

![load_manifest DAG](img/load_manifest.png)

---

## derive_components

Derives additional components from the base input (e.g. resolving entity references).

![derive_components DAG](img/derive_components.png)

---

## validate_registry

Validates the registry against schemas and constraints.

![validate_registry DAG](img/validate_registry.png)

---

## export_manifest

Exports the registry back to entity-centered YAML format.

![export_manifest DAG](img/export_manifest.png)

---

## base_etl

Base ETL utilities shared across dataflows.

![base_etl DAG](img/base_etl.png)

---

## Audits

### requirement_coverage

Checks that all requirements have at least one solution.

![audit_requirement_coverage DAG](img/audit_requirement_coverage.png)

---

### traceability

Checks that all solutions can be traced back to a requirement.

![audit_traceability DAG](img/audit_traceability.png)

---

### todo

Checks for unresolved TODO items in the solution.

![audit_todo DAG](img/audit_todo.png)
