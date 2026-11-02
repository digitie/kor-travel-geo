"""API 이미지의 실제 시작 명령이 access log에 공개 API 키 값을 남기지 않는지 확인한다."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

_REPO = Path(__file__).resolve().parents[2]
# 가짜 값이다. 실제 키를 테스트에 넣지 않는다.
_SECRET = "SECRET123456"


def _shipped_api_command() -> list[str]:
    command_line = next(
        line.removeprefix("CMD ")
        for line in (_REPO / "docker/api.Dockerfile").read_text().splitlines()
        if line.startswith("CMD ")
    )
    command = json.loads(command_line)
    assert command[:2] == ["sh", "-c"]
    assert "uvicorn kortravelgeo.api.app:app" in command[2]
    return [str(part) for part in command]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_live(process: subprocess.Popen[bytes], base_url: str, log_path: Path) -> None:
    deadline = time.monotonic() + 90
    while True:
        assert process.poll() is None, f"API가 준비 전에 종료됨:\n{log_path.read_text()}"
        with contextlib.suppress(httpx.TransportError):
            if httpx.get(f"{base_url}/v1/healthz", timeout=2).status_code == 200:
                return
        assert time.monotonic() < deadline, f"API 준비 시간 초과:\n{log_path.read_text()}"
        time.sleep(0.2)


def _stop(process: subprocess.Popen[bytes]) -> None:
    # 본 시험이 만든 새 session/group만 정리한다. Docker/운영 프로세스는 호출하지 않는다.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux 이미지 shell·프로세스 계약")
def test_shipped_api_cmd_access_log_masks_query_api_key(tmp_path: Path) -> None:
    """이미지 CMD로 띄운 실제 uvicorn의 access log에 ``?key=`` 값이 남지 않아야 한다.

    PATH 앞의 ``uvicorn``은 실제 uvicorn CLI를 이미지 CMD 인자 그대로 실행하고
    ``--lifespan off``만 덧붙여 DB 없이 기동한다. 로깅 설정과 앱 import 순서는 이미지와 같은
    CLI 경로를 탄다.
    """
    shim = tmp_path / "uvicorn"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m uvicorn "$@" --lifespan off\n')
    shim.chmod(0o700)
    port = _free_port()
    environment = dict(os.environ)
    environment.update(
        PATH=str(tmp_path) + os.pathsep + environment.get("PATH", ""),
        PYTHONPATH=str(_REPO / "src"),
        KTG_API_HOST="127.0.0.1",
        PORT=str(port),
    )
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "api.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            _shipped_api_command(),
            env=environment,
            cwd=tmp_path,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            _wait_until_live(process, base_url, log_path)
            httpx.post(
                f"{base_url}/v2/geocode?key={_SECRET}",
                json={"query": "서울특별시 중구 세종대로 110"},
                timeout=30,
            )
        finally:
            _stop(process)

    output = log_path.read_text()
    assert _SECRET not in output
    access_lines = [line for line in output.splitlines() if '"POST /v2/geocode?' in line]
    assert len(access_lines) == 1, output
    assert '"POST /v2/geocode?key=*** HTTP/1.1"' in access_lines[0]
