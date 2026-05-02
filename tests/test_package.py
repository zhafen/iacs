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


def test_mcp_functions_work_with_installed_library():
    """Verify the MCP functions work and the interpreter is from a venv install.

    When running via ``uv run pytest`` or after a ``pip install``, sys.executable
    will be inside a virtualenv (.venv) or a site-packages-managed location,
    not a bare system Python.  This catches the case where tests accidentally
    run against the system interpreter with no installed package.
    """
    exe = sys.executable
    assert ".venv" in exe or "site-packages" in exe, (
        f"Expected sys.executable to be inside a virtualenv or site-packages "
        f"install (typical of uv/pip), but got: {exe}\n"
        "Run tests via 'uv run pytest' to use the project virtualenv."
    )

    result = subprocess.run(
        [
            exe,
            "-c",
            "from iacs.mcp_server import _build_format_description; "
            "out = _build_format_description(); "
            "assert 'description' in out, 'missing description'; "
            "print('ok')",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"MCP _build_format_description() failed:\n{result.stderr}"
    )
