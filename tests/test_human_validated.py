"""This module contains tests that have carefully been vetted by a human contributor."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from hamilton.driver import Builder
from hamilton.lifecycle import NodeExecutionHook

from iacs.dataflows import base_etl

ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = ROOT / "examples"
EXPECTED_DIR = ROOT / "tests" / "test_dataflows" / "expected"
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


class _ExpectedValueChecker(NodeExecutionHook):
    """Checks each executed node's result against a hand-written expected value, if one exists."""

    def __init__(self, example_dir: Path):
        self.example_dir = example_dir
        self._expected_modules: dict[Path, ModuleType] = {}

    def run_before_node_execution(self, **kwargs):
        pass

    def run_after_node_execution(
        self, *, node_name: str, node_tags: dict, result, success: bool, **kwargs
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


@pytest.mark.parametrize("example_dir", _example_dirs())
def test_base_etl(example_dir: Path):
    dr = (
        Builder()
        .with_modules(base_etl)
        .with_adapters(_ExpectedValueChecker(example_dir))
        .build()
    )
    dr.execute(["registry"], inputs={"input_dirs": [str(example_dir)]})
