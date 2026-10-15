"""API 이미지의 실제 shell CMD가 종료 신호와 옵션을 보존하는지 확인한다."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux 이미지 shell·프로세스 계약")
@pytest.mark.parametrize("configured", [False, True])
def test_api_cmd_exec_preserves_pid_sigterm_and_host_port(
    tmp_path: Path, configured: bool
) -> None:
    """실제 CMD를 로컬 대역 실행기로 실행해 PID·SIGTERM과 기본/명시 옵션을 검사한다."""
    command_line = next(
        line.removeprefix("CMD ")
        for line in (_REPO / "docker/api.Dockerfile").read_text().splitlines()
        if line.startswith("CMD ")
    )
    command = json.loads(command_line)
    assert command[:2] == ["sh", "-c"]
    ready = tmp_path / "ready.json"
    terminated = tmp_path / "terminated"
    executable = tmp_path / "uvicorn"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, signal, sys, time\n"
        "from pathlib import Path\n"
        "def stop(signum, frame):\n"
        "    Path(os.environ['KTG_SIGNAL_PROBE_STOP']).write_text('SIGTERM')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "ready = Path(os.environ['KTG_SIGNAL_PROBE_READY'])\n"
        "pending = ready.with_suffix('.tmp')\n"
        "pending.write_text(json.dumps({'pid': os.getpid(), 'argv': sys.argv[1:]}))\n"
        "pending.replace(ready)\n"
        "while True: time.sleep(1)\n"
    )
    executable.chmod(0o700)
    environment = dict(os.environ)
    environment.update(
        PATH=str(tmp_path) + os.pathsep + environment.get("PATH", ""),
        KTG_SIGNAL_PROBE_READY=str(ready),
        KTG_SIGNAL_PROBE_STOP=str(terminated),
    )
    for key in ("KTG_API_HOST", "PORT"):
        environment.pop(key, None)
    if configured:
        environment.update(KTG_API_HOST="127.0.0.7", PORT="23456")
    process = subprocess.Popen(
        command,
        env=environment,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert process.poll() is None, "API 대역이 준비 전에 종료됨"
            assert time.monotonic() < deadline, "API 대역 준비 시간 초과"
            time.sleep(0.01)
        observed = json.loads(ready.read_text())
        assert observed["pid"] == process.pid, "shell을 exec해 API가 직접 신호를 받아야 함"
        assert observed["argv"] == [
            "kortravelgeo.api.app:app",
            "--host",
            "127.0.0.7" if configured else "0.0.0.0",
            "--port",
            "23456" if configured else "12501",
        ]
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert terminated.read_text() == "SIGTERM"
    finally:
        # 본 시험이 만든 새 session/group만 정리한다. Docker/운영 프로세스는 호출하지 않는다.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
