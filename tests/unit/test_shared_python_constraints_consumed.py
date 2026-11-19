"""공용 제약이 실제 API/CS/CI 설치에 전달되고 pip resolver가 구버전을 거부하는 계약."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

from test_gdal_cache_boundary import instructions

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "docker/constraints-shared-python.txt"
CS = ROOT / "kor-travel-geo-dagster/docker/constraints-dagster.txt"


class SharedPythonConsumptionTests(unittest.TestCase):
    def test_api_install_consumes_copied_shared_constraints_and_pip_check(self):
        rows = instructions("docker/api.Dockerfile")
        self.assertIn(
            ("COPY", "docker/constraints-shared-python.txt ./docker/constraints-shared-python.txt"),
            rows,
        )
        command = next(
            value
            for kind, value in rows
            if kind == "RUN" and 'pip install -e ".[api,loaders]"' in value
        )
        self.assertIn("-c ./docker/constraints-shared-python.txt", command)
        self.assertIn(
            next(line for line in SHARED.read_text().splitlines() if line.startswith("pip==")),
            command,
        )
        self.assertIn("&& python -m pip check", command)

    def test_code_location_keeps_its_family_constraints_and_includes_shared(self):
        rows = instructions("kor-travel-geo-dagster/docker/dagster.Dockerfile")
        self.assertIn(
            ("COPY", "docker/constraints-shared-python.txt ./docker/constraints-shared-python.txt"),
            rows,
        )
        command = next(
            value
            for kind, value in rows
            if kind == "RUN" and "pip install --prefix=/install" in value
        )
        self.assertIn("-c ./kor-travel-geo-dagster/docker/constraints-dagster.txt", command)
        self.assertIn("-c ../../docker/constraints-shared-python.txt", CS.read_text().splitlines())
        self.assertIn("--only-binary=gdal", command)
        self.assertIn('"gdal==' + chr(36) + '{GDAL_VERSION}"', command)

    def test_ci_root_installs_and_policy_use_the_same_consumed_constraints(self):
        text = (ROOT / ".github/workflows/ci.yml").read_text()
        installs = [
            line for line in text.splitlines() if 'pip install -e ".[api,loaders,dev]"' in line
        ]
        self.assertEqual(len(installs), 2)
        self.assertTrue(all("-c docker/constraints-shared-python.txt" in line for line in installs))
        self.assertIn("--constraints docker/constraints-shared-python.txt", text)
        self.assertIn("--constraints kor-travel-geo-dagster/docker/constraints-dagster.txt", text)
        self.assertIn("--python-version 3.12", text)
        self.assertIn("--strict-python-application --python-build-tools", text)

    def test_build_backends_use_the_same_approved_tool_pins(self):
        pins = dict(
            line.split("==", 1)
            for line in SHARED.read_text().splitlines()
            if line and not line.startswith("#")
        )
        for file in (ROOT / "pyproject.toml", ROOT / "kor-travel-geo-dagster/pyproject.toml"):
            values = tomllib.loads(file.read_text())["build-system"]["requires"]
            self.assertEqual(
                set(values), {f"setuptools=={pins['setuptools']}", f"wheel=={pins['wheel']}"}
            )

    def test_runtime_pip_is_installed_after_prefix_copy_with_pure_wheel_cache(self):
        rows = instructions("kor-travel-geo-dagster/docker/dagster.Dockerfile")
        copied = rows.index(("COPY", "--from=builder /install /usr/local"))
        index, command = next(
            (i, value)
            for i, (kind, value) in enumerate(rows)
            if kind == "RUN" and "pip install --only-binary=:all: --upgrade pip==" in value
        )
        self.assertGreater(index, copied)
        self.assertIn("sharing=locked", command)
        self.assertIn("PIP_CACHE_DIR=/root/.cache/pip/pure-python-tools", command)
        self.assertIn("env -u PIP_NO_CACHE_DIR", command)
        self.assertIn(
            next(line for line in SHARED.read_text().splitlines() if line.startswith("pip==")),
            command,
        )
        self.assertIn("&& python -m pip check", command)

    def test_public_pip_resolver_accepts_exact_and_rejects_old_shared_transitive(self):
        # 가짜 순수 wheel metadata만 해석한다. 실제 grpcio 설치·import·다운로드는 없다.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for version, expected in (("1.85.3", 0), ("1.84.0", 1)):
                wheel = root / f"grpcio-{version}-py3-none-any.whl"
                info = f"grpcio-{version}.dist-info/"
                with zipfile.ZipFile(wheel, "w") as z:
                    z.writestr(
                        info + "METADATA",
                        f"Metadata-Version: 2.1\nName: grpcio\nVersion: {version}\n",
                    )
                    z.writestr(
                        info + "WHEEL",
                        "Wheel-Version: 1.0\nGenerator: geo-contract-fixture\n"
                        "Root-Is-Purelib: true\nTag: py3-none-any\n",
                    )
                    z.writestr(info + "RECORD", "")
                for constraint in (SHARED, CS):
                    with self.subTest(version=version, constraint=constraint.name):
                        report = root / ("report-" + constraint.name + ".json")
                        result = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "pip",
                                "--isolated",
                                "install",
                                "--dry-run",
                                "--ignore-installed",
                                "--no-index",
                                "--no-deps",
                                "--disable-pip-version-check",
                                "-c",
                                str(constraint),
                                "--report",
                                str(report),
                                str(wheel),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=20,
                        )
                        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                        if expected == 0:
                            self.assertEqual(
                                json.loads(report.read_text())["install"][0]["metadata"]["version"],
                                version,
                            )
                        else:
                            self.assertIn("ResolutionImpossible", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
