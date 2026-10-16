"""이미지의 최종 interpreter bytecode 준비와 API 생존 점검 계약."""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from packaging.requirements import Requirement

_ROOT = Path(__file__).resolve().parents[2]
_COMMON_COMMIT = "344d91c0eec4b605e007e61ce248693a729d692d"
_BUILD_ARGV = ["-I", "-m", "kortravelcommon.build_bytecode", "--stdlib"]


def _instructions(path: str) -> list[tuple[str, str]]:
    text = re.sub(r"\\\n", " ", (_ROOT / path).read_text())
    return [
        (match[1].upper(), match[2])
        for line in text.splitlines()
        if (match := re.match(r"^(FROM|RUN|COPY|USER|HEALTHCHECK)\s+(.*)", line))
    ]


@pytest.mark.parametrize("path", [
    "docker/api.Dockerfile", "kor-travel-geo-dagster/docker/dagster.Dockerfile",
])
def test_final_runtime_compiles_stdlib_once_as_root_after_common_install(
    path: str, tmp_path: Path,
) -> None:
    instructions = _instructions(path)
    builds = [
        (index, value) for index, (kind, value) in enumerate(instructions)
        if kind == "RUN" and "kortravelcommon.build_bytecode" in value
    ]
    assert len(builds) == 1
    index, command = builds[0]
    assert command == "python -I -m kortravelcommon.build_bytecode --stdlib"
    stage = max(i for i, (kind, _) in enumerate(instructions[:index]) if kind == "FROM")
    assert stage == max(i for i, (kind, _) in enumerate(instructions) if kind == "FROM")
    users = [value for kind, value in instructions[stage:index] if kind == "USER"]
    assert not users or users[-1] in {"root", "0"}
    # 최종 interpreter의 stdlib를 덮는 COPY가 뒤에 오면 cache 준비가 무효화된다.
    assert not any(
        kind == "COPY" and (
            shlex.split(value)[-1] == "/usr/local"
            or shlex.split(value)[-1].startswith("/usr/local/lib/")
        )
        for kind, value in instructions[index + 1:]
    )
    install_before = instructions[stage:index]
    assert any(
        (kind == "COPY" and value == "--from=builder /install /usr/local")
        or (kind == "RUN" and 'python -m pip install -e ".[api,loaders]"' in value)
        for kind, value in install_before
    )
    probe = tmp_path / "python"
    output = tmp_path / "argv.json"
    probe.write_text(
        "#!" + os.sys.executable + "\nimport json,os,sys; "
        "open(os.environ['ARGV_OUT'],'w').write(json.dumps(sys.argv[1:])); "
        "sys.exit(int(os.environ.get('PROBE_EXIT','0')))\n"
    )
    probe.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path), ARGV_OUT=str(output))
    result = subprocess.run(["/bin/sh", "-c", command], env=env, check=False)
    assert result.returncode == 0
    assert json.loads(output.read_text()) == _BUILD_ARGV
    # 컴파일 실패를 뒤의 무조건 성공으로 감추지 않는다.
    result = subprocess.run(
        ["/bin/sh", "-c", command], env={**env, "PROBE_EXIT": "1"}, check=False,
    )
    assert result.returncode == 1


def test_common_is_api_only_core_dependency_and_same_pin_as_code_server() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text())["project"]
    assert all(Requirement(value).name != "kor-travel-common" for value in project["dependencies"])
    api = [Requirement(value) for value in project["optional-dependencies"]["api"]]
    common = next(value for value in api if value.name == "kor-travel-common")
    assert common.extras == set()
    assert common.url == (
        "git+https://github.com/digitie/kor-travel-common.git@"
        f"{_COMMON_COMMIT}#subdirectory=packages/py/kor-travel-common"
    )
    dagster = tomllib.loads(
        (_ROOT / "kor-travel-geo-dagster/pyproject.toml").read_text(),
    )["project"]["dependencies"]
    server = next(Requirement(value) for value in dagster if Requirement(value).name == common.name)
    assert server.url == common.url
    assert server.extras == {"dagster", "grpc-health"}


@pytest.mark.parametrize(("port", "expected"), [(None, "12501"), ("14321", "14321")])
def test_api_health_uses_public_loopback_liveness_and_runtime_port(
    port: str | None, expected: str, tmp_path: Path,
) -> None:
    instruction = next(value for kind, value in _instructions("docker/api.Dockerfile")
                       if kind == "HEALTHCHECK")
    options, command = instruction.split(" CMD ", 1)
    assert options == "--interval=30s --timeout=5s --retries=12 --start-period=30s"
    argv = json.loads(command)
    assert argv[:2] == ["sh", "-c"]
    output = tmp_path / "health.json"
    probe = tmp_path / "python"
    probe.write_text(
        "#!" + os.sys.executable + "\nimport json,os,sys; "
        "open(os.environ['ARGV_OUT'],'w').write(json.dumps(sys.argv[1:])); "
        "sys.exit(int(os.environ.get('PROBE_EXIT','0')))\n"
    )
    probe.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if key != "PORT"}
    env.update(PATH=str(tmp_path), ARGV_OUT=str(output))
    if port is not None:
        env["PORT"] = port
    for exit_code in (0, 1):
        result = subprocess.run(
            ["/bin/sh", "-c", argv[2]], env={**env, "PROBE_EXIT": str(exit_code)}, check=False,
        )
        assert result.returncode == exit_code
        assert json.loads(output.read_text()) == [
            "-I", "-m", "kortravelcommon.http_health", "--port", expected,
            "--path", "/v1/healthz", "--timeout-seconds", "4",
        ]


@pytest.mark.parametrize(("status", "expected"), [(200, 0), (302, 1), (503, 1)])
def test_installed_api_cli_is_quiet_header_only_without_app_or_db_imports(
    status: int, expected: int,
) -> None:
    source = """
import importlib.abc
import runpy
import sys
class BlockHeavy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"dagster", "grpc", "sqlalchemy", "kortravelgeo"}:
            raise AssertionError("health imported optional application")
sys.meta_path.insert(0, BlockHeavy())
sys.argv = ["kortravelcommon.http_health", "--port", sys.argv[1],
            "--path", "/v1/healthz", "--timeout-seconds", "1"]
runpy.run_module("kortravelcommon.http_health", run_name="__main__")
"""
    seen: list[bytes] = []
    with socket.socket() as listener, ThreadPoolExecutor(max_workers=1) as pool:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        port = listener.getsockname()[1]

        def serve() -> None:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(3)
                request = b""
                while b"\r\n\r\n" not in request:
                    part = conn.recv(4096)
                    assert part
                    request += part
                    assert len(request) <= 16_384
                seen.append(request)
                # 본문이 없는 경우에도 완전한 2xx 헤더만으로 생존을 판정하는 명시 계약.
                conn.sendall(
                    f"HTTP/1.0 {status} response\r\nContent-Length: 100\r\n\r\n".encode()
                )

        future = pool.submit(serve)
        env = dict(os.environ, http_proxy="http://127.0.0.1:1")
        result = subprocess.run(
            [os.sys.executable, "-I", "-c", source, str(port)], env=env,
            capture_output=True, text=True, timeout=5, check=False,
        )
        future.result(timeout=5)
    assert result.returncode == expected
    assert result.stdout == result.stderr == ""
    assert len(seen) == 1
    assert seen[0].split(b"\r\n", 1)[0] == b"GET /v1/healthz HTTP/1.0"
