"""This module contains tests that have carefully been vetted by a human contributor."""

from pathlib import Path

from hamilton.driver import Builder
from hamilton.lifecycle import NodeExecutionHook
import pytest

from iacs.dataflows import base_etl

ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = ROOT / "examples"
EXPECTED_DIR = ROOT / "expected"


def _example_dirs() -> list:
    params = [
        pytest.param(example_dir, id=example_dir.name)
        for example_dir in sorted(EXAMPLES_DIR.iterdir())
    ]
    return params


class NodeInspector(NodeExecutionHook):
    def __init__(self):
        self.results = {}

    def run_before_node_execution(self, *, node_name, node_kwargs, **kwargs):
        pass  # inspect inputs here if needed

    def run_after_node_execution(self, *, node_name, result, success, error, **kwargs):
        pass


@pytest.mark.parametrize("example_dir", _example_dirs())
def test_base_etl(example_dir: Path):

    dr = (
        Builder()
        .with_modules(base_etl)
        .with_adapters(inspector := NodeInspector())
        .build()
    )
    dr.execute(["registry"], inputs={"input_dirs": [str(example_dir)]})
    # inspector.results now holds every intermediate node's output
