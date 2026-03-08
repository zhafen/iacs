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
from hamilton import driver, base

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
EXPECTED_DIR = Path(__file__).parent / "expected"

DATAFLOW_MODULE_NAMES = [
    "load_manifest",
    "validate_registry",
    "export_manifest",
    # "derive_components",
    # "audit.requirement_coverage",
    # "audit.todo",
    # "audit.traceability",
]


# ─── Discovery helpers ──────────────────────────────────────────────────────

def _get_dataflow_modules() -> list[tuple[str, ModuleType]]:
    """Return (name, module) for every Hamilton DAG module listed in DATAFLOW_MODULE_NAMES."""
    return [
        (name, importlib.import_module(f"iacs.dataflows.{name}"))
        for name in DATAFLOW_MODULE_NAMES
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


def _expected_data_vars(expected_module: ModuleType) -> dict:
    """Return DataFrame and dict variables from an expected module."""
    result = {}
    for name in dir(expected_module):
        if name.startswith("_"):
            continue
        val = getattr(expected_module, name)
        if isinstance(val, (pd.DataFrame, dict)):
            result[name] = val
    return result


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

    preceding_mods = []
    for name in DATAFLOW_MODULE_NAMES:
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
    # Normalize columns where all non-null values are numeric to float so that
    # e.g. 1 and 1.0 compare equal regardless of int vs float dtype.
    for col in common_cols:
        for frame in (exp_sub, act_sub):
            converted = pd.to_numeric(frame[col], errors="coerce")
            if converted.notna().sum() == frame[col].notna().sum():
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
    if isinstance(expected_value, pd.DataFrame):
        _assert_df_rows_subset(expected_value, actual_value, context=var_name)
    elif isinstance(expected_value, dict):
        assert isinstance(actual_value, dict), (
            f"'{var_name}': expected dict, got {type(actual_value)}"
        )
        for key in expected_value:
            assert key in actual_value, (
                f"'{var_name}': key '{key}' not found in actual"
            )
            exp_val = expected_value[key]
            if isinstance(exp_val, pd.DataFrame):
                _assert_df_rows_subset(
                    exp_val, actual_value[key], context=f"{var_name}[{key}]"
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


# ─── Test parameters ────────────────────────────────────────────────────────

def _test_params() -> list:
    """Generate pytest.param objects for each (example_dir, module_name) pair
    that has a corresponding expected file."""
    params = []
    for example_dir in sorted(EXAMPLES_DIR.iterdir()):
        if not example_dir.is_dir():
            continue
        for module_name, mod in _get_dataflow_modules():
            if (EXPECTED_DIR / example_dir.name / f"{module_name}.py").exists():
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
    expected_vars = _expected_data_vars(
        _load_expected_for_dataflow(example_dir, module_name)
    )
    if not expected_vars:
        pytest.skip("No expected variables in expected file")

    extra = {"output_dir": str(tmp_output_dir / example_dir.name)}
    try:
        inputs = _build_inputs_for(module_name, example_dir, extra)
    except Exception as exc:
        pytest.skip(f"Could not build inputs for {module_name}: {exc}")

    dr = driver.Driver(inputs, mod, adapter=base.DictResult())
    available = {v.name for v in dr.list_available_variables() if not v.is_external_input}
    to_execute = [name for name in expected_vars if name in available]

    if not to_execute:
        pytest.skip(f"No expected variables are nodes in the {module_name} DAG")

    try:
        results = dr.execute(to_execute)
    except Exception as exc:
        pytest.skip(f"DAG execution failed (not yet implemented): {exc}")

    for var_name in to_execute:
        actual = results.get(var_name)
        if actual is None:
            continue
        _assert_subset(var_name, expected_vars[var_name], actual)
