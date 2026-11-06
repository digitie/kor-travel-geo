"""API 이미지의 실제 시작 명령이 access log에 공개 API 키 값을 남기지 않는지 확인한다."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from uvicorn.logging import AccessFormatter

from kortravelgeo.api.app import create_app
from kortravelgeo.api.log_redaction import (
    SecretQueryParamFilter,
    install_log_redaction,
    redact_secret_query_params,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

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


_LOGGER_NAMES = ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore")


@pytest.fixture
def restore_loggers() -> Iterator[None]:
    """시험이 바꾼 uvicorn/httpx logger 상태(레벨·handler·filter)를 원래대로 돌린다."""
    saved = {}
    for name in _LOGGER_NAMES:
        logger = logging.getLogger(name)
        saved[name] = (
            logger.level,
            list(logger.handlers),
            list(logger.filters),
            logger.propagate,
            logger.disabled,
        )
    try:
        yield
    finally:
        for name, (level, handlers, filters, propagate, disabled) in saved.items():
            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.handlers[:] = handlers
            logger.filters[:] = filters
            logger.propagate = propagate
            logger.disabled = disabled


def _capture(logger_name: str, formatter: logging.Formatter) -> io.StringIO:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger(logger_name)
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.disabled = False
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    return stream


@pytest.mark.parametrize(
    "name",
    [
        "key", "KEY", "Key", "apikey", "apiKey", "api_key", "API-KEY",
        "servicekey", "serviceKey", "service_key", "confmKey",
        "token", "access_token", "Access-Token", "secret", "client_secret",
        "password", "PASSWORD",
        # Starlette은 이름을 percent-decode해서 읽는다(``%6Bey`` == ``key``).
        "%6Bey", "k%65y", "api%5Fkey",
    ],
)
def test_redact_secret_query_params_masks_value_and_keeps_name(name: str) -> None:
    text = f"/v2/geocode?address=seoul&{name}={_SECRET}&type=road"

    assert redact_secret_query_params(text) == f"/v2/geocode?address=seoul&{name}=***&type=road"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"/v2/reverse?key={_SECRET}", "/v2/reverse?key=***"),
        (f"/v2/reverse?key={_SECRET}&key=again", "/v2/reverse?key=***&key=***"),
        (f"/x?a=1;token={_SECRET};b=2", "/x?a=1;token=***;b=2"),
        (f"/x?key={_SECRET}%2B%2F%3D%3D&n=1", "/x?key=***&n=1"),
        (f"/x?key={_SECRET}==#frag", "/x?key=***"),
        (f"/x?key=&apikey={_SECRET}", "/x?key=***&apikey=***"),
        # Starlette은 ``&``로만 나누므로 ``AB;CD``·탭 포함 값 전체가 키다. 꼬리를 남기지 않는다.
        (f"/x?key=AB;{_SECRET}&n=1", "/x?key=***&n=1"),
        (f"/x?key=AB\t{_SECRET}&n=1", "/x?key=***&n=1"),
        (
            "Server error '500 Internal Server Error' for url "
            f"'https://example.invalid/download?serviceKey={_SECRET}&downloadKnd=1'",
            "Server error '500 Internal Server Error' for url "
            "'https://example.invalid/download?serviceKey=***&downloadKnd=1'",
        ),
    ],
)
def test_redact_secret_query_params_examples(text: str, expected: str) -> None:
    assert redact_secret_query_params(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "/v1/healthz",
        "/v1/address/search?query=key%3Dvalue&keyword=seoul&page=1&size=10",
        "/v2/geocode?address=key&type=road",
        "keyword=only-a-fragment-without-separator",
    ],
)
def test_redact_secret_query_params_keeps_non_secret_text(text: str) -> None:
    assert redact_secret_query_params(text) == text


def test_access_log_line_is_masked_through_uvicorn_formatter(restore_loggers: None) -> None:
    install_log_redaction()
    stream = _capture(
        "uvicorn.access",
        AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False),
    )

    # uvicorn h11/httptools 구현이 쓰는 access log 호출 모양 그대로다.
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:50000",
        "GET",
        f"/v2/reverse?x=127&y=37&KEY={_SECRET}",
        "1.1",
        200,
    )

    assert stream.getvalue() == (
        '127.0.0.1:50000 - "GET /v2/reverse?x=127&y=37&KEY=*** HTTP/1.1" 200 OK\n'
    )


def test_uvicorn_error_masks_websocket_line_and_traceback(restore_loggers: None) -> None:
    install_log_redaction()
    stream = _capture("uvicorn.error", logging.Formatter("%(message)s"))
    logger = logging.getLogger("uvicorn.error")

    logger.info('%s - "WebSocket %s" 403', "127.0.0.1:50000", f"/v2/geocode?key={_SECRET}")
    request = httpx.Request("GET", "https://example.invalid/download", params={
        "serviceKey": _SECRET, "downloadKnd": "1",
    })
    try:
        httpx.Response(500, request=request).raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Exception in ASGI application\n", exc_info=exc)

    output = stream.getvalue()
    assert _SECRET not in output
    assert '"WebSocket /v2/geocode?key=***" 403' in output
    assert "download?serviceKey=***&downloadKnd=1" in output
    assert "httpx.HTTPStatusError" in output


class _RebuildingFormatter(logging.Formatter):
    """JSON/rich formatter처럼 캐시된 exc_text 대신 exc_info에서 traceback을 다시 만든다."""

    def format(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def test_masked_traceback_is_not_rebuilt_from_exc_info(restore_loggers: None) -> None:
    install_log_redaction()
    stream = _capture("uvicorn.error", _RebuildingFormatter())
    request = httpx.Request("GET", "https://example.invalid/x", params={"serviceKey": _SECRET})
    try:
        httpx.Response(500, request=request).raise_for_status()
    except httpx.HTTPStatusError as exc:
        logging.getLogger("uvicorn.error").error("boom", exc_info=exc)

    assert _SECRET not in stream.getvalue()


def test_httpx_request_log_is_quiet_and_masked(restore_loggers: None) -> None:
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    install_log_redaction()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING

    # 운영자가 httpx를 INFO로 내려도 provider 키는 남지 않는다.
    stream = _capture("httpx", logging.Formatter("%(message)s"))
    logging.getLogger("httpx").setLevel(logging.INFO)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        client.get(
            "https://api.vworld.invalid/req/address",
            params={"key": _SECRET, "address": "seoul"},
        )
        client.get(
            "https://business.juso.invalid/addrlink/addrLinkApi.do",
            params={"confmKey": _SECRET, "keyword": "seoul"},
        )

    output = stream.getvalue()
    assert _SECRET not in output
    assert "GET https://api.vworld.invalid/req/address?key=***&address=seoul" in output
    assert "addrLinkApi.do?confmKey=***&keyword=seoul" in output


def test_operator_configured_httpx_level_is_kept(restore_loggers: None) -> None:
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    install_log_redaction()
    assert logging.getLogger("httpx").level == logging.DEBUG


def test_filter_survives_uvicorn_logging_config_applied_after_app() -> None:
    """``uvicorn.run(app)``처럼 앱을 먼저 만든 뒤 uvicorn logging 설정을 적용해도 가린다.

    ``dictConfig``는 전역 handler를 닫으므로 pytest 프로세스가 아닌 별도 interpreter에서 본다.
    """
    source = (
        "import logging, logging.config\n"
        "from kortravelgeo.api.app import app\n"
        "from uvicorn.config import LOGGING_CONFIG\n"
        "logging.config.dictConfig(LOGGING_CONFIG)\n"
        "logging.getLogger('uvicorn.access').info('%s - \"%s %s HTTP/%s\" %d',\n"
        f"    '127.0.0.1:1', 'GET', '/v2/reverse?key={_SECRET}', '1.1', 200)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        env=dict(os.environ, PYTHONPATH=str(_REPO / "src")),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert _SECRET not in result.stdout + result.stderr
    assert '"GET /v2/reverse?key=*** HTTP/1.1" 200' in result.stdout


def test_create_app_installs_redaction_once(restore_loggers: None) -> None:
    for name in ("uvicorn.access", "uvicorn.error", "httpx"):
        logging.getLogger(name).filters[:] = []

    create_app()
    create_app()

    for name in ("uvicorn.access", "uvicorn.error", "httpx"):
        filters = logging.getLogger(name).filters
        assert sum(isinstance(item, SecretQueryParamFilter) for item in filters) == 1, name
