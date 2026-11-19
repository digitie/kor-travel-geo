"""GDAL 컴파일 경계와 실제 Dockerfile shell 명령의 wheel 재사용 계약."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_API = "docker/api.Dockerfile"
_CS = "kor-travel-geo-dagster/docker/dagster.Dockerfile"


def instructions(path: str) -> list[tuple[str, str]]:
    text = re.sub(r"\\\n", " ", (_ROOT / path).read_text())
    return [
        (m[1], m[2])
        for line in text.splitlines()
        if (m := re.match(r"^(FROM|RUN|COPY)\s+(.*)", line))
    ]


def gdal_build(path: str) -> tuple[int, str]:
    found = [
        (i, value)
        for i, (kind, value) in enumerate(instructions(path))
        if kind == "RUN"
        and 'GDAL_VERSION="$(gdal-config --version)"' in value
        and "parallel=1" in value
    ]
    if len(found) != 1:
        raise AssertionError("GDAL 직렬 컴파일 RUN은 하나여야 한다")
    return found[0]


class GdalCacheBoundaryTests(unittest.TestCase):
    def test_gdal_build_precedes_every_project_copy(self) -> None:
        for path in (_API, _CS):
            with self.subTest(path=path):
                index, command = gdal_build(path)
                self.assertFalse(any(kind == "COPY" for kind, _ in instructions(path)[:index]))
                self.assertNotIn(".[loaders]", command)
                self.assertNotIn(".[api,loaders]", command)
                self.assertNotIn("constraints-dagster", command)

    def test_code_server_builds_only_gdal_wheel_and_installs_it_with_constraints(self) -> None:
        _, build = gdal_build(_CS)
        self.assertIn("pip wheel --no-deps --wheel-dir=/opt/ktg-gdal-wheels", build)
        self.assertIn('"gdal==${GDAL_VERSION}"', build)
        install = next(
            value
            for kind, value in instructions(_CS)
            if kind == "RUN" and "pip install --prefix=/install" in value
        )
        self.assertIn("--only-binary=gdal", install)
        self.assertIn("/opt/ktg-gdal-wheels/*.whl", install)
        self.assertIn("-c ./kor-travel-geo-dagster/docker/constraints-dagster.txt", install)
        self.assertIn('"gdal==${GDAL_VERSION}" ".[loaders]" ./kor-travel-geo-dagster', install)

    def test_same_locked_mount_only_on_gdal_build_commands(self) -> None:
        mount = "--mount=type=cache,id=geo-gdal-py312,target=/root/.cache/pip,sharing=locked"
        for path in (_API, _CS):
            with self.subTest(path=path):
                _, command = gdal_build(path)
                self.assertTrue(command.startswith(mount + " "))
                self.assertIn(
                    "env -u PIP_NO_CACHE_DIR HOME=/tmp/ktg-gdal-build-home "
                    "PIP_CACHE_DIR=/root/.cache/pip python -m pip",
                    re.sub(r"\s+", " ", command),
                )
                self.assertEqual((_ROOT / path).read_text().count(mount), 1)
                self.assertIn("PIP_NO_CACHE_DIR=1", (_ROOT / path).read_text())
                # 정확한 libgdal pin과 최종 binding/lib 버전 비교를 유지한다.
                self.assertIn('"gdal==${GDAL_VERSION}"', command)
                self.assertIn("if lib_version not in python_version:", (_ROOT / path).read_text())
                bases = [value for kind, value in instructions(path) if kind == "FROM"]
                self.assertTrue(all(value.startswith("python:3.12") for value in bases))

    def test_actual_shell_cache_environment_is_gdal_only(self) -> None:
        for path in (_API, _CS):
            with self.subTest(path=path):
                calls, _ = self._shell(path)
                gdal = [row for row in calls if row["parallelOne"]]
                self.assertEqual(len(gdal), 1)
                self.assertIsNone(gdal[0]["noCache"])
                self.assertTrue(gdal[0]["cacheDir"].endswith("/pip-cache"))
                other = [row for row in calls if not row["parallelOne"]]
                self.assertGreaterEqual(len(other), 2)  # pip 자체 갱신과 앱 설치.
                for row in other:
                    self.assertEqual(row["noCache"], "1")
                    self.assertIsNone(row["cacheDir"])

    def _shell(self, path: str, fail_build: bool = False) -> tuple[list[dict], int]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bindir = root / "bin"
            bindir.mkdir()
            log = root / "calls.jsonl"
            probe = bindir / "python"
            probe.write_text(
                "#!"
                + sys.executable
                + "\n"
                + r"""import json,os,sys
from pathlib import Path
args=sys.argv[1:]
config=Path(os.environ.get("HOME", "/"))/".pydistutils.cfg"
build=any(x.startswith("gdal==") for x in args) and "--prefix=/install" not in args
row={"args":args,"parallelOne":config.exists() and config.read_text()=="[build_ext]\nparallel=1\n",
     "noCache":os.environ.get("PIP_NO_CACHE_DIR"),"cacheDir":os.environ.get("PIP_CACHE_DIR")}
with open(os.environ["PROBE_LOG"],"a") as out:out.write(json.dumps(row)+"\n")
if build:
    assert row["parallelOne"], "직렬 컴파일 설정이 실제 HOME에 있어야 한다"
    if os.environ.get("FAIL_GDAL")=="1":sys.exit(7)
if "wheel" in args:
    wheel=next(x.split("=",1)[1] for x in args if x.startswith("--wheel-dir="))
    p=Path(wheel);p.mkdir(parents=True);(p/"gdal-3.10.3-cp312-cp312-linux_aarch64.whl").write_bytes(b"local-wheel-stub")
if "--prefix=/install" in args:
    assert "--only-binary=gdal" in args
    wheels=[Path(x) for x in args if x.endswith(".whl")]
    assert len(wheels)==1 and wheels[0].read_bytes()==b"local-wheel-stub"
"""
            )
            probe.chmod(0o700)
            gdal = bindir / "gdal-config"
            gdal.write_text("#!/bin/sh\nprintf '3.10.3\\n'\n")
            gdal.chmod(0o700)
            _, command = gdal_build(path)
            # Docker의 mount 선언만 제거하고 실제 shell 부분과 환경 범위는 실행한다.
            command = re.sub(r"^--mount=\S+\s+", "", command)
            commands = [command.split("&& python - <<", 1)[0]]
            if path == _CS:
                commands.append(
                    next(
                        value
                        for kind, value in instructions(path)
                        if kind == "RUN" and "pip install --prefix=/install" in value
                    )
                )
            else:
                commands.append(
                    next(
                        value
                        for kind, value in instructions(path)
                        if kind == "RUN" and 'pip install -e ".[api,loaders]"' in value
                    ).split("&& python - <<", 1)[0]
                )
            script = " && ".join(commands).replace("/tmp/ktg-gdal-build-home", str(root / "home"))
            script = script.replace("/opt/ktg-gdal-wheels", str(root / "wheels"))
            script = script.replace("/root/.cache/pip", str(root / "pip-cache"))
            result = subprocess.run(
                ["/bin/sh", "-ec", script],
                cwd=root,
                env={
                    **{k: v for k, v in os.environ.items() if k != "PIP_CACHE_DIR"},
                    "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                    "HOME": str(root / "default-home"),
                    "PROBE_LOG": str(log),
                    "PIP_NO_CACHE_DIR": "1",
                    "FAIL_GDAL": "1" if fail_build else "0",
                },
                capture_output=True,
                text=True,
                timeout=5,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            if not fail_build:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((root / "home").exists())
            return calls, result.returncode

    def test_actual_api_build_shell_retains_serial_compile_and_cleanup(self) -> None:
        calls, _ = self._shell(_API)
        compile_call = next(row for row in calls if "gdal==3.10.3" in row["args"])
        self.assertTrue(compile_call["parallelOne"])
        self.assertEqual(sum(".[api,loaders]" in row["args"] for row in calls), 1)

    def test_actual_code_server_shell_reuses_its_built_wheel(self) -> None:
        calls, _ = self._shell(_CS)
        self.assertEqual(sum("wheel" in row["args"] for row in calls), 1)
        self.assertEqual(sum("--prefix=/install" in row["args"] for row in calls), 1)

    def test_failed_gdal_build_stops_before_application_install(self) -> None:
        calls, code = self._shell(_CS, fail_build=True)
        self.assertEqual(code, 7)
        self.assertFalse(any("--prefix=/install" in row["args"] for row in calls))


if __name__ == "__main__":
    unittest.main()
