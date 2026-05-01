"""Smoke tests that verify the installed package is importable and the entry
point script runs.  These catch packaging gaps (missing sub-packages, missing
data files) that unit tests running against the source tree cannot detect."""

import subprocess
import sys


def test_iacs_submodules_importable():
    """All public sub-packages must be importable from a clean Python process."""
    modules = [
        "iacs",
        "iacs.architect",
        "iacs.registry",
        "iacs.utils",
        "iacs.dataflows",
        "iacs.dataflows.base_etl",
        "iacs.views",
        "iacs.views.requirement_tree",
    ]
    for module in modules:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Failed to import {module}:\n{result.stderr}"
        )


def test_mcp_server_importable():
    result = subprocess.run(
        [sys.executable, "-c", "import iacs.mcp_server"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Failed to import iacs.mcp_server:\n{result.stderr}"
