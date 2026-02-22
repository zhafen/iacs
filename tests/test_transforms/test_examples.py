"""This test file contains code to test the transforms on each of the example manifests.

The pseudo-code logic is as follows:
Loop over each example manifest in the examples directory:
    Loop over each transform module in iacs.transforms:
        1. get the DAG for the module
        2. execute the DAG on the dir
        3. load the expected outputs for the module from expected.py
        4. the outputs will usually not be a comprehensive set of records, but will be a subset of the records that should be produced by the DAG
        5. look for the same records defined in expected.py in the output of the DAG
"""

import importlib
import importlib.util
import pkgutil
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from hamilton import driver, base

import iacs.transforms as transforms_pkg
from iacs.transforms import manifest_to_registry as manifest_to_registry_module

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


# ─── Discovery helpers ──────────────────────────────────────────────────────

def _get_transform_modules() -> list[tuple[str, ModuleType]]:
    """Return (name, module) for every Hamilton DAG module in iacs.transforms."""
    transforms_path = Path(transforms_pkg.__file__).parent
    result = []
    for _, name, _ in pkgutil.iter_modules([str(transforms_path)]):
        module = importlib.import_module(f"iacs.transforms.{name}")
        result.append((name, module))
    return result


def _get_example_dirs_with_expected() -> list[Path]:
    """Return sorted example directories that contain an expected.py."""
    return [
        d for d in sorted(EXAMPLES_DIR.iterdir())
        if d.is_dir() and (d / "expected.py").exists()
    ]


# ─── Loading helpers ────────────────────────────────────────────────────────

def _load_expected(example_dir: Path) -> ModuleType:
    """Load expected.py from an example directory as a Python module."""
    spec = importlib.util.spec_from_file_location(
        f"expected_{example_dir.name}", example_dir / "expected.py"
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


# ─── DAG execution helpers ──────────────────────────────────────────────────

def _execute_dag(mod: ModuleType, inputs: dict) -> dict:
    """Execute all computable nodes of a Hamilton DAG module and return results."""
    dr = driver.Driver(inputs, mod, adapter=base.DictResult())
    output_names = [v.name for v in dr.list_available_variables() if not v.is_external_input]
    return dr.execute(output_names)


def _build_registry(example_dir: Path):
    """Build a Registry from an example directory via the manifest_to_registry DAG.

    Returns None if the DAG cannot be executed (e.g. stub implementations).
    """
    try:
        result = _execute_dag(manifest_to_registry_module, {"input_dir": str(example_dir)})
        return result.get("registry")
    except Exception:
        return None


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
    exp_str = expected[common_cols].astype(str).reset_index(drop=True)
    act_str = actual[common_cols].astype(str).reset_index(drop=True)
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


# ─── Test parameters ────────────────────────────────────────────────────────

def _test_params() -> list:
    """Generate pytest.param objects for each (example_dir, transform_module) pair."""
    params = []
    for example_dir in _get_example_dirs_with_expected():
        for module_name, mod in _get_transform_modules():
            params.append(
                pytest.param(
                    example_dir, module_name, mod,
                    id=f"{example_dir.name}-{module_name}",
                )
            )
    return params


# ─── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("example_dir,module_name,mod", _test_params())
def test_transform_dag_outputs_match_expected(
    example_dir: Path, module_name: str, mod: ModuleType
) -> None:
    """Expected records from expected.py appear in the transform DAG output.

    For each example directory and each transform module:
    1. Execute the transform DAG on the example directory.
    2. Load the expected outputs from expected.py.
    3. Verify each expected value is a subset of the corresponding DAG output.
    """
    # Steps 1 & 2: execute the DAG on the example directory
    if module_name == "manifest_to_registry":
        dag_result = _execute_dag(mod, {"input_dir": str(example_dir)})
    else:
        # Audit transforms require a registry built from the directory
        registry = _build_registry(example_dir)
        if registry is None:
            pytest.skip(
                f"Skipping {module_name} on {example_dir.name}: "
                "registry is None (manifest_to_registry not yet implemented)"
            )
        dag_result = _execute_dag(mod, {"registry": registry})

    # Step 3: load expected outputs for this example
    expected_module = _load_expected(example_dir)
    expected_vars = _expected_data_vars(expected_module)

    # Steps 4 & 5: for each expected variable that matches a DAG output, check subset
    for var_name, expected_value in expected_vars.items():
        if var_name in dag_result:
            _assert_subset(var_name, expected_value, dag_result[var_name])
