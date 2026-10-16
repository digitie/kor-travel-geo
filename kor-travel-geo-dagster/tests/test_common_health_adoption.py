"""Geo 소비 패키지의 Common 상태 조회 설치·선택 의존성 경계를 확인한다."""

from __future__ import annotations

import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from packaging.requirements import Requirement

_ROOT = Path(__file__).resolve().parents[2]
_COMMON_COMMIT = "344d91c0eec4b605e007e61ce248693a729d692d"


def test_dagster_package_installs_exact_common_with_explicit_grpc_extra() -> None:
    package = tomllib.loads((_ROOT / "kor-travel-geo-dagster/pyproject.toml").read_text())
    requirements = [Requirement(value) for value in package["project"]["dependencies"]]
    common = next(
        requirement for requirement in requirements if requirement.name == "kor-travel-common"
    )
    assert common.extras == {"dagster", "grpc-health"}
    assert common.url == (
        "git+https://github.com/digitie/kor-travel-common.git@"
        f"{_COMMON_COMMIT}#subdirectory=packages/py/kor-travel-common"
    )


def test_main_and_api_dependencies_do_not_require_common_dagster_or_grpc() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text())["project"]
    assert all(
        Requirement(value).name != "kor-travel-common" for value in project["dependencies"]
    )
    requirements = project["dependencies"] + project["optional-dependencies"]["api"]
    forbidden = {"dagster", "grpcio", "grpcio-health-checking", "protobuf"}
    assert not forbidden.intersection(Requirement(value).name for value in requirements)
    common = next(
        Requirement(value) for value in project["optional-dependencies"]["api"]
        if Requirement(value).name == "kor-travel-common"
    )
    assert not common.extras


def test_installed_common_is_the_declared_commit() -> None:
    distribution = importlib.metadata.distribution("kor-travel-common")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    assert direct_url["vcs_info"]["commit_id"] == _COMMON_COMMIT
    assert distribution.locate_file("kortravelcommon/grpc_health.py").is_file()


_BLOCK_HEAVY = """
import importlib.abc
import runpy
import sys
class BlockHeavy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"dagster", "sqlalchemy", "kortravelgeo"}:
            raise AssertionError("health must not import " + fullname)
sys.meta_path.insert(0, BlockHeavy())
sys.argv = ["kortravelcommon.grpc_health", *sys.argv[1:]]
runpy.run_module("kortravelcommon.grpc_health", run_name="__main__")
"""


def _cli(port: int, *, without_grpc: bool = False) -> subprocess.CompletedProcess[str]:
    source = _BLOCK_HEAVY
    if without_grpc:
        source = source.replace(
            'if fullname.split(".")[0] in {"dagster", "sqlalchemy", "kortravelgeo"}:',
            'if fullname.split(".")[0] in {"grpc", "grpc_health"}:\n'
            '            raise ModuleNotFoundError("optional gRPC unavailable")\n'
            '        if fullname.split(".")[0] in {"dagster", "sqlalchemy", "kortravelgeo"}:',
        )
    env = os.environ.copy()
    env.update({
        "grpc_proxy": "http://127.0.0.1:1",
        "http_proxy": "http://127.0.0.1:1",
        "https_proxy": "http://127.0.0.1:1",
    })
    return subprocess.run(
        [sys.executable, "-I", "-c", source, str(port), "--check", "live"],
        capture_output=True, text=True, timeout=8, check=False, env=env,
    )


@pytest.mark.parametrize(("serving", "expected"), [(True, 0), (False, 1)])
def test_installed_cli_uses_standard_health_without_heavy_imports(
    serving: bool, expected: int,
) -> None:
    import grpc
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    seen: list[str] = []

    class Health(health_pb2_grpc.HealthServicer):
        def Check(self, request, context):  # noqa: N802 - 표준 gRPC 메서드
            seen.append(request.service)
            return health_pb2.HealthCheckResponse(
                status=(
                    health_pb2.HealthCheckResponse.SERVING
                    if serving else health_pb2.HealthCheckResponse.NOT_SERVING
                ),
            )

    executor = ThreadPoolExecutor(max_workers=1)
    server = grpc.server(executor)
    health_pb2_grpc.add_HealthServicer_to_server(Health(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        result = _cli(port)
        assert result.returncode == expected
        assert result.stdout == result.stderr == ""
        assert seen == ["DagsterApi"]
    finally:
        server.stop(0).wait(timeout=3)
        executor.shutdown(wait=True)


def test_closed_port_is_quiet_failure_not_success() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    result = _cli(port)
    assert result.returncode == 1
    assert result.stdout == result.stderr == ""


def test_optional_grpc_absence_is_quiet_failure() -> None:
    result = _cli(1, without_grpc=True)
    assert result.returncode == 1
    assert result.stdout == result.stderr == ""


def test_installed_geo_core_does_not_import_dagster_or_grpc() -> None:
    source = """
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"dagster", "grpc", "grpc_health"}:
            raise AssertionError("core imported optional " + fullname)
sys.meta_path.insert(0, BlockOptional())
import kortravelgeo
assert kortravelgeo.AsyncAddressClient.__name__ == "AsyncAddressClient"
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", source],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
