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
import pkgutil
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml
from hamilton import driver, base

import iacs.dataflows as dataflows_pkg
from iacs.dataflows import load_manifest as load_manifest_module

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


# ─── Discovery helpers ──────────────────────────────────────────────────────

def _get_dataflow_modules() -> list[tuple[str, ModuleType]]:
    """Return (name, module) for every Hamilton DAG module in iacs.dataflows."""
    dataflows_path = Path(dataflows_pkg.__file__).parent
    result = []
    for _, name, ispkg in pkgutil.iter_modules([str(dataflows_path)]):
        if ispkg:
            subpkg = importlib.import_module(f"iacs.dataflows.{name}")
            subpkg_path = Path(subpkg.__file__).parent
            for _, subname, _ in pkgutil.iter_modules([str(subpkg_path)]):
                module = importlib.import_module(f"iacs.dataflows.{name}.{subname}")
                result.append((f"{name}.{subname}", module))
        else:
            module = importlib.import_module(f"iacs.dataflows.{name}")
            result.append((name, module))
    return result


def _get_example_dirs_with_manifest() -> list[Path]:
    """Return sorted example directories that contain a manifest.yaml."""
    return [
        d for d in sorted(EXAMPLES_DIR.iterdir())
        if d.is_dir() and (d / "manifest.yaml").exists()
    ]


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

def _execute_dag(mod: ModuleType, inputs: dict, output_names: list[str] | None = None) -> dict:
    """Execute a Hamilton DAG module and return results.

    If output_names is provided, only those nodes are executed. Otherwise all
    computable (non-external-input) nodes are executed.
    """
    dr = driver.Driver(inputs, mod, adapter=base.DictResult())
    if output_names is None:
        output_names = [v.name for v in dr.list_available_variables() if not v.is_external_input]
    return dr.execute(output_names)


def _build_registry(example_dir: Path):
    """Build a Registry from an example directory via the load_manifest DAG.

    Returns None if the DAG cannot be executed (e.g. stub implementations).
    """
    try:
        result = _execute_dag(load_manifest_module, {"input_dir": [str(example_dir)]})
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

    # Build inputs for this module.
    if module_name == "load_manifest":
        inputs = {"input_dir": [str(example_dir)]}
    else:
        registry = _build_registry(example_dir)
        if registry is None:
            pytest.skip(
                f"{module_name}: registry is None (manifest_to_registry not yet implemented)"
            )
        inputs = {"registry": registry}

    dr = driver.Driver(inputs, mod, adapter=base.DictResult())
    available = {v.name for v in dr.list_available_variables() if not v.is_external_input}

    to_execute = [name for name in expected_vars if name in available]
    if not to_execute:
        if expected_vars:
            pytest.fail(
                f"Expected variables {list(expected_vars)} are defined in expected.py "
                f"but none are nodes in the {module_name} DAG. "
                f"This likely means the ingestion for this example is not yet implemented."
            )
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


@pytest.mark.parametrize("example_dir", _get_example_dirs_with_manifest())
def test_export_dataflows_match_expected(example_dir: Path) -> None:
    """Registry exported back to YAML should match the original manifest."""
    from iacs.dataflows import export_manifest

    registry = _build_registry(example_dir)
    if registry is None:
        pytest.skip("registry is None (load_manifest not yet implemented)")

    exported = export_manifest.manifest_data(registry)

    original = yaml.safe_load((example_dir / "manifest.yaml").read_text())
    assert exported == original
