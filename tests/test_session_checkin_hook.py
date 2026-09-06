import os
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4


HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "session-checkin.sh"


def _run_hook(payload, *, env=None, timeout=None):
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        env=env,
        text=True,
        check=False,
        timeout=timeout,
    )


def test_uses_dedicated_subdirectory_within_scratchpad_dir(tmp_path):
    result = _run_hook({"scratchpad_dir": str(tmp_path), "session_id": "session-1"})

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "session-checkin" / "turn-count").read_text() == "1\n"
    assert not (tmp_path / "turn-count").exists()


def test_blocks_on_turn_2_then_every_8_turns(tmp_path):
    payload = {"scratchpad_dir": str(tmp_path), "session_id": "session-1"}
    outputs = []

    for _ in range(10):
        result = _run_hook(payload)
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout.strip())

    assert outputs[0] == ""
    assert json.loads(outputs[1])["decision"] == "block"
    assert outputs[2] == ""
    assert outputs[9] and json.loads(outputs[9])["decision"] == "block"


def test_stop_hook_active_exits_without_reblocking_or_counting(tmp_path):
    result = _run_hook(
        {
            "scratchpad_dir": str(tmp_path),
            "session_id": "session-1",
            "stop_hook_active": True,
        }
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "session-checkin").exists()


def test_counter_updates_are_serialized(tmp_path):
    counter_dir = tmp_path / "session-checkin"
    counter_dir.mkdir()
    (counter_dir / "turn-count").write_text("1\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cat_wrapper = bin_dir / "cat"
    cat_wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$#" -eq 1 ] && [ "${1##*/}" = "turn-count" ]; then\n'
        "  sleep 0.1\n"
        "fi\n"
        'exec /bin/cat "$@"\n'
    )
    cat_wrapper.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    payload = {"scratchpad_dir": str(tmp_path), "session_id": "session-1"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: _run_hook(payload, env=env), range(2)))

    assert all(result.returncode == 0 for result in results)
    assert (counter_dir / "turn-count").read_text() == "3\n"
    assert sum(bool(result.stdout.strip()) for result in results) == 1


def test_stale_lock_exits_without_hanging(tmp_path):
    counter_dir = tmp_path / "session-checkin"
    counter_dir.mkdir()
    (counter_dir / "turn-count").write_text("1\n")
    (counter_dir / ".lock").mkdir()

    result = _run_hook(
        {"scratchpad_dir": str(tmp_path), "session_id": "session-1"},
        timeout=2,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert (counter_dir / "turn-count").read_text() == "1\n"


def test_missing_lock_dir_in_cleanup_does_not_fail(tmp_path):
    counter_dir = tmp_path / "session-checkin"
    counter_dir.mkdir()
    (counter_dir / "turn-count").write_text("1\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cat_wrapper = bin_dir / "cat"
    cat_wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$#" -eq 1 ] && [ "${1##*/}" = "turn-count" ]; then\n'
        f"  rmdir {counter_dir / '.lock'}\n"
        "fi\n"
        'exec /bin/cat "$@"\n'
    )
    cat_wrapper.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    result = _run_hook({"scratchpad_dir": str(tmp_path), "session_id": "session-1"}, env=env)

    assert result.returncode == 0, result.stderr
    assert (counter_dir / "turn-count").read_text() == "2\n"


def test_sanitizes_session_id_for_tmp_fallback():
    marker = f"session-checkin-{uuid4().hex}"
    session_id = f"../../{marker}"
    safe_dir = Path("/tmp/claude-session-checkin") / marker
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
