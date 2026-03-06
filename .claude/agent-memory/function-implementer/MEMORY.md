# Function Implementer Memory

## iacs Project Patterns

### Schema conventions in load_manifest.py
- `component_index` is always `int32` (from `t["_idx"].cast("int32")` in `keyvalue_store`)
- When building DataFrames to union with YAML-derived ibis tables, always cast:
  `df["component_index"] = df["component_index"].astype("int32")`
- `modifier` column always uses `pd.StringDtype()` for nullable string type

### Test conventions
- Tests live in `tests/test_dataflows/test_load_manifest.py`
- Test runner: `uv run pytest` (not `pytest` or `python -m pytest`)
- Test fixtures use `tmp_path` (pytest built-in) for temp files
- Existing tests call `spine(kvs)` and `component_tables(kvs)` with one arg — new CSV params have `None` defaults

### File structure
- Main dataflow: `/Users/zhafen/repos/iacs/iacs/dataflows/load_manifest.py`
- Test file: `/Users/zhafen/repos/iacs/tests/test_dataflows/test_load_manifest.py`
- `dhash` utility: `/Users/zhafen/repos/iacs/iacs/utils.py` — returns first 12 hex chars of SHA-256
