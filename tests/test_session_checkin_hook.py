import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "session-checkin.sh"


def _run_hook(payload):
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def test_uses_dedicated_subdirectory_within_scratchpad_dir(tmp_path):
    result = _run_hook({"scratchpad_dir": str(tmp_path), "session_id": "session-1"})

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "session-checkin" / "turn-count").read_text() == "1\n"
    assert not (tmp_path / "turn-count").exists()


def test_sanitizes_session_id_for_tmp_fallback():
    marker = f"session-checkin-{uuid4().hex}"
    session_id = f"../../{marker}"
    safe_dir = Path("/tmp/claude-session-checkin") / hashlib.sha256(session_id.encode()).hexdigest()
    escaped_dir = Path("/tmp") / marker

    shutil.rmtree(safe_dir, ignore_errors=True)
    shutil.rmtree(escaped_dir, ignore_errors=True)

    try:
        result = _run_hook({"session_id": session_id})

        assert result.returncode == 0, result.stderr
        assert (safe_dir / "turn-count").read_text() == "1\n"
        assert not escaped_dir.exists()
    finally:
        shutil.rmtree(safe_dir, ignore_errors=True)
        shutil.rmtree(escaped_dir, ignore_errors=True)
