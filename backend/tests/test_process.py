"""Black-box tests of `python -m doctorholiday`: startup errors, logging and SIGTERM."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.conftest import TEST_ENV

STARTUP_TIMEOUT_S = 15


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _environ(tmp_path: Path, **overrides: str | None) -> dict[str, str]:
    # Only what Python needs plus our variables: the developer's own env must not leak in.
    environ = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), **TEST_ENV}
    for key, value in overrides.items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = value
    return environ


def _json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_missing_variable_exits_with_clear_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "doctorholiday"],
        env=_environ(tmp_path, SESSION_SECRET=None, MFA_ENCRYPTION_KEY="key-sentinel"),
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT_S,
        check=False,
    )

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "Traceback" not in output
    assert "key-sentinel" not in output
    assert "db-password-sentinel" not in output
    (entry,) = _json_lines(result.stdout)
    assert entry["level"] == "CRITICAL"
    assert "SESSION_SECRET: is missing" in entry["errors"]
    assert any(str(error).startswith("MFA_ENCRYPTION_KEY: ") for error in entry["errors"])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_serves_and_shuts_down_gracefully_on_sigterm(tmp_path: Path) -> None:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "doctorholiday"],
        env=_environ(tmp_path, PORT=str(port), LOG_LEVEL="INFO"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as resp:
                    assert resp.status == 200
                    assert json.load(resp) == {"status": "ok"}
                break
            except OSError:
                assert process.poll() is None, "server exited during startup"
                assert time.monotonic() < deadline, "server did not start"
                time.sleep(0.1)

        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=STARTUP_TIMEOUT_S)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

    # uvicorn re-raises the signal after a graceful shutdown, so the exit status reports SIGTERM
    # (143 in Kubernetes), as expected for a process stopped by the kubelet.
    assert process.returncode == -signal.SIGTERM
    assert stderr == ""
    entries = _json_lines(stdout)
    messages = [entry["message"] for entry in entries]
    assert any("Uvicorn running" in str(message) for message in messages)
    assert any("Finished server process" in str(message) for message in messages)
    for secret in (
        "db-password-sentinel",
        TEST_ENV["SESSION_SECRET"],
        TEST_ENV["MFA_ENCRYPTION_KEY"],
    ):
        assert secret not in stdout
