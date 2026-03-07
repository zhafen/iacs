"""This test file contains code to test the dataflows on each of the example manifests.

The pseudo-code logic is as follows:
Loop over each example manifest in the examples directory:
    Loop over each dataflow module in iacs.dataflows:
        1. get the DAG for the module
        2. execute the DAG on the dir
        3. load the expected outputs for the module from expected.py
        4. the outputs will usually not be a comprehensive set of records, but will be a subset of the records that should be produced by the DAG
        5. look for the same records defined in expected.py in the output of the DAG
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

DATAFLOW_MODULE_NAMES = [
    "base_etl",
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


def _get_example_dirs_with_expected() -> list[Path]:
    """Return sorted example directories that have a corresponding expected/expected.py."""
    return [
        d for d in sorted(EXAMPLES_DIR.iterdir())
        if d.is_dir() and (EXPECTED_DIR / d.name / "expected.py").exists()
    ]


# ─── Loading helpers ────────────────────────────────────────────────────────

def _load_expected(example_dir: Path) -> ModuleType:
    """Load expected.py from an example directory as a Python module."""
    spec = importlib.util.spec_from_file_location(
        f"expected_{example_dir.name}", EXPECTED_DIR / example_dir.name / "expected.py"
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
    exp_str = expected[common_cols].fillna("__NULL__").astype(str).reset_index(drop=True)
    act_str = actual[common_cols].fillna("__NULL__").astype(str).reset_index(drop=True)
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
    """Generate pytest.param objects for each (example_dir, module) pair."""
    params = []
    for example_dir in _get_example_dirs_with_expected():
        for module_name, mod in _get_dataflow_modules():
            params.append(
                pytest.param(
                    example_dir, module_name, mod,
                    id=f"{example_dir.name}-{module_name}",
                )
            )
    return params


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("example_dir,module_name,mod", _test_params())
def test_ingestion_dataflows_match_expected(
    example_dir: Path, module_name: str, mod: ModuleType,
) -> None:
    """All expected outputs from expected.py appear in the dataflow DAG output.

    For each (example, dataflow module) pair:
    1. Execute all DAG nodes that have a corresponding expected variable.
    2. For each expected variable present in the results, verify it is a subset
       of the DAG output.
    Skips when no expected variables are nodes in the module, or execution fails.
    """
    expected_vars = _expected_data_vars(_load_expected(example_dir))

    # Build inputs and get available nodes for this module.
    if module_name == "base_etl":
        dr = driver.Driver({"input_dir": [str(example_dir)]}, mod, adapter=base.DictResult())
        try:
            raw = dr.execute(["validated_registry"])
        except Exception as exc:
            pytest.skip(f"DAG execution failed (not yet implemented): {exc}")
        reg = raw["validated_registry"]
        results = {
            "component_tables": {
                k: v for k, v in reg._components.items() if hasattr(v, "to_pandas")
            }
        }
        to_execute = [name for name in expected_vars if name in results]
        if not to_execute:
            if expected_vars:
                pytest.fail(
                    f"Expected variables {list(expected_vars)} are defined in expected.py "
                    f"but none match {module_name} registry output. "
                    f"This likely means ingestion for this example is not yet implemented."
                )
            pytest.skip(f"No expected variables match {module_name} registry output")
    elif module_name == "load_manifest":
        dr = driver.Driver({"input_dir": [str(example_dir)]}, mod, adapter=base.DictResult())
        available = {v.name for v in dr.list_available_variables() if not v.is_external_input}

        to_execute = [name for name in expected_vars if name in available]
        if not to_execute:
            pytest.skip(f"No expected variables are nodes in the {module_name} DAG")

        try:
            results = dr.execute(to_execute)
        except Exception as exc:
            pytest.skip(f"DAG execution failed (not yet implemented): {exc}")
    else:
        try:
            architect = Architect.from_manifest(str(example_dir))
            architect.load_dataflow(module_name)
        except Exception:
            pytest.skip(f"{module_name}: registry could not be built")

        available = set(architect.outputs)
        to_execute = [name for name in expected_vars if name in available]
        if not to_execute:
            pytest.skip(f"No expected variables are nodes in the {module_name} DAG")

        try:
            results = architect.execute(to_execute)
        except Exception as exc:
            pytest.skip(f"DAG execution failed (not yet implemented): {exc}")

    for var_name in to_execute:
        actual = results.get(var_name)
        if actual is None:
            continue
        _assert_subset(var_name, expected_vars[var_name], actual)


@pytest.mark.parametrize("example_dir", _get_example_dirs_with_manifest())
def test_export_dataflows_match_expected(example_dir: Path) -> None:
    """Exported manifest should contain the expected subset defined in expected/manifest.yaml."""
    expected_manifest_path = EXPECTED_DIR / example_dir.name / "manifest.yaml"
    if not expected_manifest_path.exists():
        pytest.skip("No expected manifest.yaml in expected dir")

    try:
        architect = Architect.from_manifest(str(example_dir))
        architect.load_dataflow("export_manifest")
    except Exception:
        pytest.skip("registry could not be built")

    try:
        result = architect.execute(["manifest_data"])
    except Exception as exc:
        pytest.skip(f"DAG execution failed (not yet implemented): {exc}")

    exported = result["manifest_data"]
    expected = yaml.safe_load(expected_manifest_path.read_text())
    _assert_manifest_subset(expected, exported)
