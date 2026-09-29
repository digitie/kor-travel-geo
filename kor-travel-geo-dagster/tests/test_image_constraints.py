"""Contract tests for the image's exact-version install (dagster-shared plan stage 0, T-324).

On the shared Dagster plane the host (webserver/daemon) version must be >= every code-server's
(Dagster backcompat policy). The image installed unlocked from pyproject floors, so any rebuild
could resolve a newer dagster than the host. ``docker/constraints-dagster.txt`` is now the one
place the exact versions live, and these tests bind the Dockerfile, pyproject and the installed
environment to it. No network, no Docker.
"""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_DIR.parent
_DOCKER_DIR = _PACKAGE_DIR / "docker"
_CONSTRAINTS = _DOCKER_DIR / "constraints-dagster.txt"
_DOCKERFILE = _DOCKER_DIR / "dagster.Dockerfile"
_CONSTRAINTS_IN_BUILD_CONTEXT = "./kor-travel-geo-dagster/docker/constraints-dagster.txt"

_DAGSTER_CORE_FAMILY = (
    "dagster",
    "dagster-webserver",
    "dagster-graphql",
    "dagster-pipes",
    "dagster-shared",
)


def _constraints() -> dict[str, Version]:
    pins: dict[str, Version] = {}
    for raw in _CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.]*)", line)
        assert match, f"constraints line must be an exact `name==version` pin: {raw!r}"
        name = canonicalize_name(match.group(1))
        assert name not in pins, f"duplicate constraint: {name}"
        pins[name] = Version(match.group(2))
    return pins


def test_constraints_pin_the_dagster_family_to_one_version() -> None:
    pins = _constraints()
    versions = {pins[name] for name in _DAGSTER_CORE_FAMILY}
    assert len(versions) == 1, versions
    (core,) = versions
    # Dagster's library packages track core as 0.(minor+16).micro (1.13.24 <-> 0.29.24).
    assert pins["dagster-postgres"] == Version(f"0.{core.minor + 16}.{core.micro}")


def test_constraints_cover_the_shared_major_libraries() -> None:
    # The dagster-shared plan §3 set that crosses projects. asyncpg is not installed by geo.
    assert {
        "pydantic",
        "pydantic-core",
        "pydantic-settings",
        "psycopg",
        "psycopg2-binary",
        "grpcio",
        "protobuf",
        "sqlalchemy",
    } <= set(_constraints())


def _dockerfile_run_commands() -> list[str]:
    # Join backslash continuations so each RUN is one logical command.
    text = re.sub(r"\\\n", " ", _DOCKERFILE.read_text(encoding="utf-8"))
    return [line for line in text.splitlines() if line.startswith("RUN ")]


def test_dockerfile_installs_the_code_location_under_the_constraints() -> None:
    installs = [
        cmd
        for cmd in _dockerfile_run_commands()
        if "pip install" in cmd and "./kor-travel-geo-dagster" in cmd
    ]
    assert installs, "no pip install of ./kor-travel-geo-dagster found in dagster.Dockerfile"
    for cmd in installs:
        assert f"-c {_CONSTRAINTS_IN_BUILD_CONTEXT}" in cmd, cmd
    # The whole kor-travel-geo-dagster dir (constraints included) is in the build context.
    assert "COPY kor-travel-geo-dagster ./kor-travel-geo-dagster" in _DOCKERFILE.read_text(
        encoding="utf-8"
    )


def test_dockerfile_base_images_are_one_digest_pinned_python_312() -> None:
    bases = re.findall(r"^FROM\s+(\S+)", _DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(bases) == 2, bases
    # builder and runtime share one base: the GDAL binding built in the builder links the
    # libgdal of that debian release.
    assert len(set(bases)) == 1, bases
    assert re.fullmatch(r"python:3\.12-slim@sha256:[0-9a-f]{64}", bases[0]), bases[0]


def _declared_requirements() -> list[Requirement]:
    requirements: list[Requirement] = []
    for pyproject in (_REPO_ROOT / "pyproject.toml", _PACKAGE_DIR / "pyproject.toml"):
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
        requirements.extend(Requirement(dep) for dep in project["dependencies"])
    return requirements


def test_constraints_satisfy_the_declared_floors() -> None:
    # A constraint outside a pyproject range would make the image resolve fail; catch it here.
    pins = _constraints()
    checked: set[str] = set()
    for requirement in _declared_requirements():
        name = canonicalize_name(requirement.name)
        pinned = pins.get(name)
        if pinned is None:
            continue
        checked.add(name)
        assert requirement.specifier.contains(pinned, prereleases=True), (requirement, pinned)
    # The comparison really ran against the declared deps (not an empty intersection).
    assert {"dagster", "dagster-webserver", "dagster-postgres", "sqlalchemy", "psycopg"} <= checked


@pytest.mark.parametrize("name", sorted(_constraints()))
def test_installed_environment_matches_the_constraints(name: str) -> None:
    """The CI ``dagster`` job installs with the same ``-c`` file as the image.

    This binds the test run to the versions the image ships, so the suite exercises exactly
    those. A package the environment does not have (e.g. psycopg-binary on a source install)
    is skipped, not failed.
    """
    try:
        installed = Version(importlib.metadata.version(name))
    except importlib.metadata.PackageNotFoundError:
        pytest.skip(f"{name} not installed in this environment")
    assert installed == _constraints()[name]
