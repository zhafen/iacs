"""This module contains tests that have carefully been vetted by a human contributor."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from hamilton.driver import Builder
from hamilton.lifecycle import NodeExecutionHook

from iacs.dataflows import base_etl
from iacs.dataflows.etl import export_manifest

ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = ROOT / "examples"
EXPECTED_DIR = ROOT / "tests" / "test_dataflows" / "expected"
TEMP_DIR = ROOT / "tests" / "test_dataflows" / "temp"
DATAFLOWS_MODULE_PREFIX = "iacs.dataflows."


def _example_dirs() -> list:
    return [
        pytest.param(example_dir, id=example_dir.name)
        for example_dir in sorted(EXAMPLES_DIR.iterdir())
        if example_dir.is_dir()
    ]


def _load_expected_module(expected_filepath: Path) -> ModuleType:
    """Import a per-dataflow expected file (e.g. ``etl/load_manifest.py``) as a module."""
    spec = importlib.util.spec_from_file_location(
        expected_filepath.stem, expected_filepath
    )
    expected_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(expected_module)
    return expected_module


# ─── Comparison helpers (copied from tests/test_dataflows/test_examples.py) ──


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
    assert (
        actual is not None
    ), f"{context}: could not convert actual value to DataFrame (got {type(actual_value)})"
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
    - List item matching uses overlapping-field subset semantics.
    """
    for key, exp_val in expected.items():
        if key not in actual:
            continue
        act_val = actual[key]
        ctx = f"{context}.{key}" if context else key
        # Confirmed necessary by deleting this branch and running the suite:
        # tests/test_dataflows/expected/example/etl/load_manifest.py alone has
        # 9 sibling values (e.g. "adore_cats", "sift_cat_box") that are plain
        # lists compared against plain lists — without this branch they are
        # silently skipped (no assertion runs) rather than checked. It also
        # makes the incorrect_raw_entity_first_data negative case in
        # tests/test_dataflows/expected/minimal/etl/load_manifest.py silently
        # match, which _assert_not_subset then reports as a failure.
        if isinstance(exp_val, list) and isinstance(act_val, list):
            for exp_item in exp_val:
                found = any(
                    _manifest_item_matches(exp_item, act_item) for act_item in act_val
                )
                assert found, (
                    f"{ctx}: expected item {exp_item!r} not found in actual\n"
                    f"  Actual: {act_val!r}"
                )
        # Needed for e.g. raw_entity_first_data["make_cats_happy"] in
        # tests/test_dataflows/expected/example/etl/load_manifest.py, which
        # nests child entities ("feed_and_water_cats", etc.) inside their
        # parent — without recursing here those nested expected values would
        # never be checked against the actual nested dict.
        elif isinstance(exp_val, dict) and isinstance(act_val, dict):
            _assert_manifest_subset(exp_val, act_val, context=ctx)
        elif isinstance(exp_val, dict):
            assert False, (
                f"{ctx}: expected dict structure but got {type(act_val).__name__} — "
                "possible hierarchical/flat format mismatch"
            )


def _assert_subset(var_name: str, expected_value, actual_value) -> None:
    """Assert expected_value is contained within actual_value using subset semantics."""
    if isinstance(expected_value, pd.DataFrame):
        _assert_df_rows_subset(expected_value, actual_value, context=var_name)

    elif isinstance(expected_value, dict):
        assert isinstance(
            actual_value, dict
        ), f"'{var_name}': expected dict, got {type(actual_value)}"
        for key in expected_value:
            assert key in actual_value, f"'{var_name}': key '{key}' not found in actual"
            exp_val = expected_value[key]
            act_val = actual_value[key]
            if isinstance(exp_val, pd.DataFrame):
                _assert_df_rows_subset(exp_val, act_val, context=f"{var_name}[{key}]")
            elif isinstance(exp_val, dict) and isinstance(act_val, dict):
                _assert_manifest_subset(
                    exp_val, act_val, context=f"{var_name}[{key!r}]"
                )


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


class _ExpectedValueChecker(NodeExecutionHook):
    """Checks each executed node's result against a hand-written expected value, if one exists."""

    def __init__(self, example_dir: Path):
        self.example_dir = example_dir
        self._expected_modules: dict[Path, ModuleType] = {}

    def run_before_node_execution(self, **kwargs):
        pass

    def run_after_node_execution(
        self, *, node_name: str, node_tags: dict, result, **kwargs
    ):

        source_module = node_tags.get("module")
        # Input variables don't have source modules
        if source_module is None:
            return

        # The part after the dataflows prefix tells us where to find the expected values
        dataflow_module_name = source_module[len(DATAFLOWS_MODULE_PREFIX) :]
        dataflow_module_subpath = dataflow_module_name.replace(".", "/")
        expected_filepath = (
            EXPECTED_DIR / self.example_dir.name / f"{dataflow_module_subpath}.py"
        )
        if not expected_filepath.exists():
            return

        # Load the module if not yet loaded
        if expected_filepath not in self._expected_modules:
            self._expected_modules[expected_filepath] = _load_expected_module(
                expected_filepath
            )
        expected_module = self._expected_modules[expected_filepath]

        # Get the expected value
        variable_name = node_name.rsplit(".", 1)[-1]
        if not hasattr(expected_module, variable_name):
            return
        expected_value = getattr(expected_module, variable_name)

        _assert_subset(node_name, expected_value, result)

        # Check we don't have incorrect values
        incorrect_name = "incorrect_" + variable_name
        if hasattr(expected_module, incorrect_name):
            incorrect_value = getattr(expected_module, incorrect_name)
            _assert_not_subset(node_name, incorrect_value, result)


@pytest.mark.parametrize("example_dir", _example_dirs())
def test_end_to_end(example_dir: Path):
    """Thorough end to end test that:
    1. Runs base_etl for each example manifest
    2. Runs export_manifest on the loaded registry
    3. Runs base_etl on the exported manifest

    In terms of comparisons, for each executed DAG node the outputs are compared to
    manually input expectations. At the end all components in the originally loaded
    registry are compared to the components of the reloaded registry.
    """

    # Get the loaded registry, comparing outputs along the way
    dr = (
        Builder()
        .with_modules(base_etl)
        .with_adapters(_ExpectedValueChecker(example_dir))
        .build()
    )
    registry = dr.execute(["registry"], inputs={"input_dirs": [str(example_dir)]})

    # Export back to manifest format, comparing outputs along the way
    dr = (
        Builder()
        .with_modules(export_manifest)
        .with_adapters(_ExpectedValueChecker(example_dir))
        .build()
    )
    output_dir = TEMP_DIR / example_dir.name
    dr.execute(
        ["exported_manifest_filepaths"],
        inputs={"registry": registry, "output_dir": output_dir},
    )

    # Reload
    dr = (
        Builder()
        .with_modules(base_etl)
        .with_adapters(_ExpectedValueChecker(example_dir))
        .build()
    )
    reloaded_registry = dr.execute(
        ["registry"], inputs={"input_dirs": [str(output_dir)]}
    )

    # Compare each component
    for comp_type in registry.component_types:
        comp = registry.get(comp_type).execute()
        loaded_comp = reloaded_registry.get(comp_type).execute()

        assert_frame_equal(comp, loaded_comp)
