# Dataflow DAGs

Hamilton DAG visualizations for iacs dataflows, grouped by the
subpackage each module lives in under `iacs/dataflows/`.
Regenerate with: `uv run python docs/gen_dag_images.py`

## `audit/`

### `audit.requirement_coverage`

![audit.requirement_coverage DAG](img/audit_requirement_coverage.png)

### `audit.todo`

![audit.todo DAG](img/audit_todo.png)

### `audit.traceability`

![audit.traceability DAG](img/audit_traceability.png)

---

## `derive/`

### `derive.derive_components`

![derive.derive_components DAG](img/derive_derive_components.png)

### `derive.impact_cost`

![derive.impact_cost DAG](img/derive_impact_cost.png)

### `derive.inherit_components`

![derive.inherit_components DAG](img/derive_inherit_components.png)

### `derive.resolve_paths`

![derive.resolve_paths DAG](img/derive_resolve_paths.png)

---

## `etl/`

### `etl.export_manifest`

![etl.export_manifest DAG](img/etl_export_manifest.png)

### `etl.load_manifest`

![etl.load_manifest DAG](img/etl_load_manifest.png)

### `etl.load_python`

![etl.load_python DAG](img/etl_load_python.png)

### `etl.load_yaml`

![etl.load_yaml DAG](img/etl_load_yaml.png)

---

## `validation/`

### `validation.validate_components`

![validation.validate_components DAG](img/validation_validate_components.png)

---

## Top-level

### `base_etl`

![base_etl DAG](img/base_etl.png)

