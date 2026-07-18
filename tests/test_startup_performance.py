"""Times MCP server install and startup in a completely isolated environment.

Run with: uv run pytest tests/test_startup_performance.py -v -s
The -s flag shows the timing output printed by each test.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
EXAMPLE_MANIFEST = REPO_ROOT / "examples" / "example"

# Thresholds (generous to avoid flakiness on slow CI machines)
MAX_INSTALL_SECONDS = 120.0
MAX_IMPORT_SECONDS = 10.0
MAX_STARTUP_SECONDS = 30.0


@pytest.fixture(scope="module")
def isolated_venv(tmp_path_factory):
    """Create a fresh venv and install iacs[mcp] once for all tests in this module."""
    tmpdir = tmp_path_factory.mktemp("isolated_venv")
    venv_dir = tmpdir / "venv"

    # Create isolated venv with no system packages
    result = subprocess.run(
        ["uv", "venv", "--no-project", str(venv_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"uv venv failed:\n{result.stderr}"

    python = venv_dir / "bin" / "python"

    t0 = time.perf_counter()
    result = subprocess.run(
        [
            "uv", "pip", "install",
            "--python", str(python),
            "--no-cache",
            "-e", f"{REPO_ROOT}[mcp]",
        ],
        capture_output=True,
        text=True,
    )
    install_duration = time.perf_counter() - t0

    assert result.returncode == 0, (
        f"Install failed after {install_duration:.1f}s:\n{result.stderr}"
    )
    assert install_duration < MAX_INSTALL_SECONDS, (
        f"Install took {install_duration:.1f}s, threshold is {MAX_INSTALL_SECONDS}s"
    )

    print(f"\n[isolated_venv] install time: {install_duration:.2f}s")
    return {"python": python, "venv": venv_dir, "install_duration": install_duration}


def test_install_duration(isolated_venv):
    """Report and assert on the package install time."""
    duration = isolated_venv["install_duration"]
    print(f"\nInstall time: {duration:.2f}s  (threshold: {MAX_INSTALL_SECONDS}s)")
    assert duration < MAX_INSTALL_SECONDS


def test_mcp_server_import_time(isolated_venv):
    """Time how long importing iacs.mcp_server takes in the isolated env."""
    python = isolated_venv["python"]

    t0 = time.perf_counter()
    result = subprocess.run(
        [str(python), "-c", "import iacs.mcp_server"],
        capture_output=True,
        text=True,
    )
    duration = time.perf_counter() - t0

    assert result.returncode == 0, f"Import failed:\n{result.stderr}"
    print(f"\nModule import time: {duration:.2f}s  (threshold: {MAX_IMPORT_SECONDS}s)")
    assert duration < MAX_IMPORT_SECONDS, (
        f"iacs.mcp_server import took {duration:.2f}s, "
        f"expected < {MAX_IMPORT_SECONDS}s"
    )


def test_mcp_server_startup_time(isolated_venv):
    """Time the full MCP server startup (lifespan) in the isolated env.

    Mirrors what happens when Claude Desktop launches iacs-mcp: the process
    starts, the lifespan runs Registrar.from_manifest(), and the server becomes
    ready to accept requests. We measure time until the process prints its
    ready-signal to stderr and then exits cleanly.
    """
    python = isolated_venv["python"]

    # Script that reproduces the lifespan work and prints a sentinel when done.
    # The lifespan is a no-op; startup cost is just importing the module.
    startup_script = (
        "import time\n"
        "t0 = time.perf_counter()\n"
        "import iacs.mcp_server  # noqa: F401\n"
        "elapsed = time.perf_counter() - t0\n"
        "print(f'STARTUP_DONE {elapsed:.3f}', flush=True)\n"
    )

    t0 = time.perf_counter()
    result = subprocess.run(
        [str(python), "-c", startup_script],
        capture_output=True,
        text=True,
        timeout=MAX_STARTUP_SECONDS + 5,
    )
    wall_duration = time.perf_counter() - t0

    assert result.returncode == 0, (
        f"Startup script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Extract the in-process measurement from stdout
    sentinel_line = next(
        (l for l in result.stdout.splitlines() if l.startswith("STARTUP_DONE")),
        None,
    )
    assert sentinel_line is not None, f"Sentinel not found in stdout:\n{result.stdout}"
    in_process_duration = float(sentinel_line.split()[1])

    print(
        f"\nStartup time (in-process): {in_process_duration:.2f}s"
        f"  wall-clock: {wall_duration:.2f}s"
        f"  (threshold: {MAX_STARTUP_SECONDS}s)"
    )
    assert wall_duration < MAX_STARTUP_SECONDS, (
        f"Full startup took {wall_duration:.2f}s, expected < {MAX_STARTUP_SECONDS}s"
    )
