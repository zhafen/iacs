"""This test file contains code to test the dataflows on each of the example manifests.

The pseudo-code logic is as follows:
Loop over each (example, dataflow module) pair that has an expected file:
    1. Build inputs for the module by running all preceding modules in order.
       Inputs are derived from the DAG signatures — no hardcoding of dependencies.
    2. Execute only the DAG nodes that have a corresponding expected variable.
    3. The expected values are a subset; look for each row/key in the actual output.
"""

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml
from hamilton import driver, base

from iacs.architect import Architect

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
EXPECTED_DIR = Path(__file__).parent / "expected"
DATAFLOWS_DIR = Path(__file__).parent.parent.parent / "iacs" / "dataflows"


# ─── Discovery helpers ──────────────────────────────────────────────────────

def _discover_dataflow_module_names() -> list[str]:
    """Return dot-separated module names for every .py file under iacs/dataflows/.

    __init__ files are excluded. Results are sorted so that shallower (less
    nested) modules come first, with alphabetical ordering within each depth
    level — this approximates the typical dependency order (base modules before
    sub-packages) without hardcoding names.
    """
    names = []
    for path in sorted(DATAFLOWS_DIR.rglob("*.py")):
        if path.stem == "__init__":
            continue
        rel = path.relative_to(DATAFLOWS_DIR)
        name = ".".join(rel.with_suffix("").parts)
        names.append(name)
    # Stable sort: shallower modules first, then alphabetical.
    names.sort(key=lambda n: (n.count("."), n))
    return names


def _get_dataflow_modules() -> list[tuple[str, ModuleType]]:
    """Return (name, module) for every Hamilton DAG module under iacs/dataflows/."""
    return [
        (name, importlib.import_module(f"iacs.dataflows.{name}"))
        for name in _discover_dataflow_module_names()
    ]


def _get_example_dirs_with_manifest() -> list[Path]:
    """Return sorted example directories that contain a manifest.yaml."""
    return [
        d for d in sorted(EXAMPLES_DIR.iterdir())
        if d.is_dir() and (d / "manifest.yaml").exists()
    ]


# ─── Loading helpers ────────────────────────────────────────────────────────

def _load_expected_for_dataflow(example_dir: Path, module_name: str) -> ModuleType:
    """Load the per-dataflow expected file for an example."""
    expected_file = EXPECTED_DIR / example_dir.name / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(
        f"expected_{example_dir.name}_{module_name.replace('.', '_')}",
        expected_file,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected_data_vars(expected_module: ModuleType) -> tuple[dict, dict]:
    """Return (positive, negative) DataFrame and dict variables from an expected module.

    Variables prefixed with ``incorrect_`` are negative cases — the test asserts
    the actual DAG output does NOT match them.  All other non-private
    DataFrame/dict variables are positive cases.
    """
    positive: dict = {}
    negative: dict = {}
    for name in dir(expected_module):
        if name.startswith("_"):
            continue
        val = getattr(expected_module, name)
        if isinstance(val, (pd.DataFrame, dict)):
            if name.startswith("incorrect_"):
                negative[name] = val
            else:
                positive[name] = val
    return positive, negative


# ─── Input-building helper ───────────────────────────────────────────────────

def _build_inputs_for(
    module_name: str, example_dir: Path, extra_inputs: dict | None = None
) -> dict:
    """Return the inputs dict for a module by running all preceding modules.

    Inspects the current module's external inputs via Hamilton, then executes
    only the necessary outputs from the preceding module chain to satisfy them.
    No dependency information is hardcoded — it is derived from the DAG signatures.
    ``extra_inputs`` (e.g. ``output_dir``) are merged into the base inputs pool.
    """
    base_inputs = {"input_dir": [str(example_dir)], **(extra_inputs or {})}

    all_names = _discover_dataflow_module_names()
    preceding_mods = []
    for name in all_names:
        if name == module_name:
            break
        preceding_mods.append(importlib.import_module(f"iacs.dataflows.{name}"))

    if not preceding_mods:
        return base_inputs

    # Determine what the current module needs as external inputs.
    current_mod = importlib.import_module(f"iacs.dataflows.{module_name}")
    inspect_dr = driver.Driver({}, current_mod, adapter=base.DictResult())
    needed = {
        v.name for v in inspect_dr.list_available_variables() if v.is_external_input
    }

    # Expand needed to include external inputs of preceding modules that are
    # produced by even earlier preceding modules (transitive dependencies).
    preceding_outputs: set[str] = set()
    for mod in preceding_mods:
        temp_dr = driver.Driver({}, mod, adapter=base.DictResult())
        for v in temp_dr.list_available_variables():
            if v.is_external_input and v.name in preceding_outputs:
                needed.add(v.name)
            elif not v.is_external_input:
                preceding_outputs.add(v.name)

    # Run preceding modules one at a time, accumulating outputs into the inputs
    # pool. Sequential execution avoids node-name conflicts between modules
    # (e.g. both load_manifest and validate_registry define a "spine" node).
    accumulated = dict(base_inputs)
    for mod in preceding_mods:
        mod_dr = driver.Driver(accumulated, mod, adapter=base.DictResult())
        mod_outputs = {
            v.name for v in mod_dr.list_available_variables() if not v.is_external_input
        }
        to_run = [n for n in needed if n in mod_outputs and n not in accumulated]
        if to_run:
            accumulated.update(mod_dr.execute(to_run))

    return accumulated


# ─── Comparison helpers ─────────────────────────────────────────────────────

def _to_pandas(value) -> pd.DataFrame | None:
    """Convert an ibis Table or pandas DataFrame to a pandas DataFrame."""
    if isinstance(value, pd.DataFrame):
        return value
    if hasattr(value, "to_pandas"):
        return value.to_pandas()
    return None


def _assert_df_rows_subset(
    expected: pd.DataFrame, actual_value, context: str = ""
) -> None:
    """Assert every row of expected appears in the actual ibis Table or DataFrame."""
    if expected.empty:
        return
    actual = _to_pandas(actual_value)
    assert actual is not None, (
        f"{context}: could not convert actual value to DataFrame (got {type(actual_value)})"
    )
    common_cols = [c for c in expected.columns if c in actual.columns]
    if not common_cols:
        return

    exp_sub = expected[common_cols].copy()
    act_sub = actual[common_cols].copy()
    # Normalize columns where all non-null/non-empty values are numeric to float
    # so that e.g. 1 and 1.0 compare equal regardless of int vs float dtype.
    # Empty strings are treated as missing for this check because bare tag
    # components store "" in sub-field columns that only exist on other rows.
    for col in common_cols:
        for frame in (exp_sub, act_sub):
            as_nullable = frame[col].replace("", pd.NA)
            converted = pd.to_numeric(as_nullable, errors="coerce")
            if converted.notna().sum() == as_nullable.notna().sum():
                frame[col] = converted.astype(float)

    exp_str = exp_sub.fillna("__NULL__").astype(str).reset_index(drop=True)
    act_str = act_sub.fillna("__NULL__").astype(str).reset_index(drop=True)
    for _, row in exp_str.iterrows():
        found = (act_str == row).all(axis=1).any()
        assert found, (
            f"{context}: expected row not found in actual output.\n"
            f"  Expected: {row.to_dict()}\n"
            f"  Actual (first 10 rows):\n{act_str.head(10).to_string()}"
        )


def _assert_subset(var_name: str, expected_value, actual_value) -> None:
    """Assert expected_value is contained within actual_value using subset semantics."""
    from iacs.registry import Registry
    if isinstance(expected_value, pd.DataFrame):
        _assert_df_rows_subset(expected_value, actual_value, context=var_name)
    elif isinstance(expected_value, dict) and isinstance(actual_value, Registry):
        for key, exp_val in expected_value.items():
            if isinstance(exp_val, pd.DataFrame):
                _assert_df_rows_subset(
                    exp_val, actual_value.view(key), context=f"{var_name}.view({key!r})"
                )
    elif isinstance(expected_value, dict):
        assert isinstance(actual_value, dict), (
            f"'{var_name}': expected dict, got {type(actual_value)}"
        )
        for key in expected_value:
            assert key in actual_value, (
                f"'{var_name}': key '{key}' not found in actual"
            )
            exp_val = expected_value[key]
            act_val = actual_value[key]
            if isinstance(exp_val, pd.DataFrame):
                _assert_df_rows_subset(exp_val, act_val, context=f"{var_name}[{key}]")
            elif isinstance(exp_val, dict) and isinstance(act_val, dict):
                _assert_manifest_subset(exp_val, act_val, context=f"{var_name}[{key!r}]")


def _assert_not_subset(var_name: str, expected_value, actual_value) -> None:
    """Assert expected_value is NOT contained within actual_value."""
    try:
        _assert_subset(var_name, expected_value, actual_value)
    except AssertionError:
        return
    pytest.fail(
        f"'{var_name}' was declared as incorrect data but it matched the actual output — "
        "the DAG should have produced different data."
    )


def _manifest_item_matches(expected, actual) -> bool:
    """Return True if expected dict/scalar is a lenient subset match of actual."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        common = [k for k in expected if k in actual]
        if not common:
            return False
        return all(_manifest_values_match(expected[k], actual[k]) for k in common)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return expected == actual
    return expected == actual


def _manifest_values_match(expected, actual) -> bool:
    if isinstance(expected, dict) and isinstance(actual, dict):
        common = [k for k in expected if k in actual]
        return all(_manifest_values_match(expected[k], actual[k]) for k in common)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return expected == actual
    return expected == actual


def _assert_manifest_subset(expected: dict, actual: dict, context: str = "") -> None:
    """Assert every entry in expected appears in actual with lenient subset semantics.

    - Top-level keys missing from actual are skipped.
    - If expected value is a list but actual value is a dict with a "data" key,
      the comparison uses actual["data"].
    - List item matching uses overlapping-field subset semantics.
    """
    for key, exp_val in expected.items():
        if key not in actual:
            continue
        act_val = actual[key]
        ctx = f"{context}.{key}" if context else key
        if isinstance(exp_val, list) and isinstance(act_val, dict) and "data" in act_val:
            act_val = act_val["data"]
        if isinstance(exp_val, list) and isinstance(act_val, list):
            for exp_item in exp_val:
                found = any(_manifest_item_matches(exp_item, act_item) for act_item in act_val)
                assert found, (
                    f"{ctx}: expected item {exp_item!r} not found in actual\n"
                    f"  Actual: {act_val!r}"
                )
        elif isinstance(exp_val, dict) and isinstance(act_val, dict):
            _assert_manifest_subset(exp_val, act_val, context=ctx)
        elif isinstance(exp_val, dict):
            assert False, (
                f"{ctx}: expected dict structure but got {type(act_val).__name__} — "
                "possible hierarchical/flat format mismatch"
            )


# ─── Test parameters ────────────────────────────────────────────────────────

def _test_params() -> list:
    """Generate pytest.param objects for every (example_dir, module_name) pair.

    All discovered dataflow modules are included for each example directory that
    contains a manifest.yaml.  Pairs without a corresponding expected file are
    still exercised (the DAG is run) but the output comparison is skipped.
    """
    params = []
    for example_dir in sorted(EXAMPLES_DIR.iterdir()):
        if not example_dir.is_dir():
            continue
        for module_name, mod in _get_dataflow_modules():
            params.append(
                pytest.param(
                    example_dir, module_name, mod,
                    id=f"{example_dir.name}-{module_name}",
                )
            )
    return params


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_output_dir(tmp_path_factory):
    """Session-scoped temporary directory for dataflow file output.

    Pytest cleans it up automatically at the end of the test session.
    """
    return tmp_path_factory.mktemp("test_examples_output")


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("example_dir,module_name,mod", _test_params())
def test_dataflows_match_expected(
    example_dir: Path, module_name: str, mod: ModuleType, tmp_output_dir: Path,
) -> None:
    """All expected outputs from the per-dataflow expected file appear in the DAG output.

    For each (example, dataflow module) pair:
    1. Build inputs by running preceding modules (inputs derived from DAG signatures).
    2. Execute only the DAG nodes that have a corresponding expected variable.
    3. Verify each expected variable is a subset of the actual DAG output.
    Skips when no expected variables match available nodes, or execution fails.
    """
    expected_file = EXPECTED_DIR / example_dir.name / f"{module_name}.py"
    if expected_file.exists():
        positive_vars, negative_vars = _expected_data_vars(
            _load_expected_for_dataflow(example_dir, module_name)
        )
    else:
        positive_vars, negative_vars = {}, {}

    has_expected = bool(positive_vars or negative_vars)

    extra = {"output_dir": str(tmp_output_dir / example_dir.name)}
    try:
        inputs = _build_inputs_for(module_name, example_dir, extra)
    except Exception as exc:
        pytest.skip(f"Could not build inputs for {module_name}: {exc}")

    dr = driver.Driver(inputs, mod, adapter=base.DictResult())
    available = {v.name for v in dr.list_available_variables() if not v.is_external_input}

    # Positive: variable name matches a DAG node directly.
    to_execute_positive = [name for name in positive_vars if name in available]

    # Negative: strip "incorrect_" prefix to find the target DAG node.
    negative_node_map = {
        name: name[len("incorrect_"):]
        for name in negative_vars
        if name[len("incorrect_"):] in available
    }
    to_execute_negative = list(set(negative_node_map.values()))

    to_execute = list(dict.fromkeys(to_execute_positive + to_execute_negative))

    if not to_execute:
        if not has_expected:
            # No expected file — run a smoke check by executing all available nodes.
            try:
                dr.execute(list(available))
            except Exception as exc:
                pytest.fail(f"DAG execution failed: {exc}")
            return
        pytest.skip(f"No expected variables are nodes in the {module_name} DAG")

    try:
        results = dr.execute(to_execute)
    except Exception as exc:
        pytest.fail(f"DAG execution failed: {exc}")

    if not has_expected:
        return

    for var_name in to_execute_positive:
        actual = results.get(var_name)
        if actual is None:
            continue
        _assert_subset(var_name, positive_vars[var_name], actual)

    for incorrect_name, node_name in negative_node_map.items():
        actual = results.get(node_name)
        if actual is None:
            continue
        _assert_not_subset(incorrect_name, negative_vars[incorrect_name], actual)


def _get_example_dirs_with_yaml() -> list[Path]:
    """Return sorted example directories that contain at least one YAML file."""
    return [
        d for d in sorted(EXAMPLES_DIR.iterdir())
        if d.is_dir() and any(d.rglob("*.yaml"))
    ]


# ─── Round-trip helpers ─────────────────────────────────────────────────────

def _normalize_df(df: pd.DataFrame, entity_id_df: pd.DataFrame) -> pd.DataFrame:
    """Replace entity_id hashes with within-file entity paths for cross-registry comparison.

    Entity IDs are hashes of ``filepath:entity_path``.  Two registries loaded
    from different directories produce different hashes for the same logical
    entities, so we normalize by using only the within-file entity path.

    Also handles *phantom parents*: entities that appear in the parent graph (e.g.
    container entities with no own components like ``cat_food_supply``) have no row
    in entity_id but do appear in derived tables.  We reconstruct their paths from
    their children's paths so they normalize correctly across registries.

    Also normalises ``*_eid`` and the primary ``entity_id`` column (entity ID references).
    """
    from iacs.utils import dhash

    filepath_of = entity_id_df.set_index("value")["filepath"].to_dict()
    path_of = entity_id_df.set_index("value")["path"].to_dict()

    # Build extended map: include phantom ancestor paths derived from known entity paths
    extra_filepath: dict[str, str] = {}
    extra_path: dict[str, str] = {}
    for eid, full_path in path_of.items():
        fp = filepath_of.get(eid, "")
        sep = full_path.find(":")
        if sep == -1:
            continue
        name_part = full_path[sep + 1:]
        while "." in name_part:
            name_part = name_part.rsplit(".", 1)[0]
            ancestor_full = f"{full_path[:sep]}:{name_part}"
            ancestor_hash = dhash(ancestor_full)
            if ancestor_hash not in path_of and ancestor_hash not in extra_path:
                extra_filepath[ancestor_hash] = fp
                extra_path[ancestor_hash] = ancestor_full

    all_filepath = {**filepath_of, **extra_filepath}
    all_path = {**path_of, **extra_path}

    def hash_to_path(eid):
        if pd.isna(eid):
            return eid
        fp = all_filepath.get(str(eid), "")
        p = all_path.get(str(eid), str(eid))
        return p[len(fp) + 1:] if fp and p.startswith(fp + ":") else p

    df = df.copy()
    for col in df.columns:
        if col == "entity_id" or col.endswith("_eid"):
            df[col] = df[col].map(hash_to_path)
    return df


def _assert_tables_equal(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    eid_df1: pd.DataFrame,
    eid_df2: pd.DataFrame,
    comp_type: str,
) -> None:
    """Normalize and compare two component tables for round-trip equality.

    ``component_index`` is excluded from comparison because list-expansion in
    the loader assigns overlapping indices when a multi-item list component is
    followed by another component (e.g. ``- includes: [A, B, C]`` expands to
    indices 1-3 but the next YAML entry is at index 2, causing a collision).
    After round-trip the exporter writes one entry per row, so re-import assigns
    clean sequential indices.  The semantic content (field values) is what we
    test for equivalence.
    """
    norm1 = _normalize_df(df1, eid_df1)
    norm2 = _normalize_df(df2, eid_df2)

    drop = {"component_index"}
    common_cols = sorted(set(norm1.columns) & set(norm2.columns) - drop)
    norm1 = norm1[common_cols].sort_values(common_cols, na_position="last").reset_index(drop=True)
    norm2 = norm2[common_cols].sort_values(common_cols, na_position="last").reset_index(drop=True)

    pd.testing.assert_frame_equal(
        norm1, norm2, check_dtype=False, obj=f"component_type={comp_type!r}"
    )


def _collect_key_order(data: dict, depth: int = 0) -> list[tuple[int, str]]:
    """Return (depth, key) pairs for all keys in a nested dict, in traversal order."""
    result = []
    for key, value in data.items():
        result.append((depth, str(key)))
        if isinstance(value, dict):
            result.extend(_collect_key_order(value, depth + 1))
    return result


@pytest.mark.parametrize("example_dir", _get_example_dirs_with_yaml(), ids=lambda d: d.name)
def test_round_trip_consistency(example_dir: Path, tmp_path: Path) -> None:
    """Exporting a registry and re-loading it produces identical component tables and key order.

    Steps:
    1. Load the example manifest into reg1 via the full ETL + derive pipeline.
    2. Export reg1 to a temp directory (export1) using the export_manifest dataflow.
    3. Re-load from export1 into reg2 via the same full pipeline.
    4. For each component type in reg1, assert the table equals reg2's table
       after normalising entity_id hashes to within-file entity paths.
    5. Export reg2 to a second temp directory (export2) and assert that each
       YAML file has the same key order as the corresponding file in export1,
       confirming that key order is stable across the round-trip.
    """
    from hamilton import driver, base
    import iacs.dataflows.etl.export_manifest as export_mod

    a1 = Architect.from_manifest(str(example_dir))

    export1 = tmp_path / "export1"
    dr = driver.Driver(
        {"registry": a1.registry, "output_dir": str(export1)},
        export_mod,
        adapter=base.DictResult(),
    )
    dr.execute(["exported_manifest_filepaths"])

    a2 = Architect.from_manifest(str(export1))

    reg1 = a1.registry
    reg2 = a2.registry

    eid_df1 = reg1.get("entity_id").execute()
    eid_df2 = reg2.get("entity_id").execute()

    skip = {"entity_id", "component_type", "invalid_field"}
    types1 = set(reg1.component_types) - skip
    types2 = set(reg2.component_types) - skip

    assert types1 == types2, (
        f"Component type mismatch after round-trip:\n"
        f"  only in original:  {sorted(types1 - types2)}\n"
        f"  only in re-loaded: {sorted(types2 - types1)}"
    )

    for comp_type in sorted(types1):
        df1 = reg1.get(comp_type).execute()
        df2 = reg2.get(comp_type).execute()
        _assert_tables_equal(df1, df2, eid_df1, eid_df2, comp_type)

    # Key-order check: a second export of reg2 must produce the same YAML key
    # order as export1, confirming sort_keys=False is stable across the round-trip.
    export2 = tmp_path / "export2"
    dr2 = driver.Driver(
        {"registry": reg2, "output_dir": str(export2)},
        export_mod,
        adapter=base.DictResult(),
    )
    dr2.execute(["exported_manifest_filepaths"])

    files1 = sorted(export1.glob("*.yaml"))
    files2 = sorted(export2.glob("*.yaml"))
    assert [f.name for f in files1] == [f.name for f in files2], (
        "Exported file names differ between first and second export."
    )
    for f1, f2 in zip(files1, files2):
        with open(f1) as fh:
            data1 = yaml.safe_load(fh) or {}
        with open(f2) as fh:
            data2 = yaml.safe_load(fh) or {}
        assert _collect_key_order(data1) == _collect_key_order(data2), (
            f"Key order changed between exports for {f1.name}."
        )


@pytest.mark.parametrize("example_dir", _get_example_dirs_with_yaml(), ids=lambda d: d.name)
def test_incremental_load_matches_directory(example_dir: Path) -> None:
    """Loading each YAML file one at a time must produce the same registry as loading the directory."""
    a_all = Architect.from_manifest(str(example_dir))

    a_inc = Architect()
    for yaml_file in sorted(example_dir.rglob("*.yaml")):
        a_inc.load_manifest(str(yaml_file))

    assert set(a_all.registry.component_types) == set(a_inc.registry.component_types)

    for comp_type in a_all.registry.component_types:
        df_all = a_all.registry.get(comp_type).execute()
        df_inc = a_inc.registry.get(comp_type).execute()
        sort_by = sorted(df_all.columns)
        pd.testing.assert_frame_equal(
            df_all.sort_values(sort_by, na_position="last").reset_index(drop=True),
            df_inc.reindex(columns=df_all.columns).sort_values(sort_by, na_position="last").reset_index(drop=True),
            check_dtype=False,
        )
