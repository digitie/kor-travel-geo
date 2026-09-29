"""Contract test for the baked-in Dagster instance config (T-322).

``docker/dagster.yaml`` is copied into the image as ``$DAGSTER_HOME/dagster.yaml``. Its storage
URL comes from kor-travel-docker-manager's ``KOR_TRAVEL_GEO_DAGSTER_PG_URL``, exposed as
``KTG_DAGSTER_PG_URL`` on the code-server, webserver and daemon services. No database is
touched: Dagster's own loader validates the file against the instance schema without
resolving env vars.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dagster._core.instance.config import dagster_instance_config

_DOCKER_DIR = Path(__file__).resolve().parents[1] / "docker"


def test_instance_config_is_valid_and_reads_storage_url_from_manager_env() -> None:
    """The manager contract is one env var holding a full URL (``postgres_url``).

    T-322 showed that ``postgres_db:`` is not a scheme-free alternative: Dagster rebuilds a URL
    with ``scheme=postgresql``, which is psycopg 3 on SQLAlchemy 2.1, and switching forms would
    need the manager to supply five env vars instead. So a change here must be coordinated with
    the manager, never incidental. The driver itself (``postgresql+psycopg2://``) is chosen in
    the manager's value; see docs/t322-dagster-storage-driver.md.
    """

    config, custom_instance_class = dagster_instance_config(str(_DOCKER_DIR))

    assert custom_instance_class is None
    assert config["storage"] == {"postgres": {"postgres_url": {"env": "KTG_DAGSTER_PG_URL"}}}
    assert config["telemetry"] == {"enabled": False}


_ENTRYPOINT = _DOCKER_DIR / "entrypoint.sh"


def _run_entrypoint(url: str | None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if url is not None:
        env["KTG_DAGSTER_PG_URL"] = url
    return subprocess.run(
        ["sh", str(_ENTRYPOINT), "echo", "started"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
@pytest.mark.parametrize(
    "url",
    ["postgresql+psycopg2://u:p@127.0.0.1:11000/kor_travel_geo_dagster", None, ""],
)
def test_entrypoint_starts_the_service_on_psycopg2_or_unset_url(url: str | None) -> None:
    result = _run_entrypoint(url)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "started"


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
@pytest.mark.parametrize(
    ("url", "scheme"),
    [
        ("postgresql://u:secret@127.0.0.1:11000/db", "postgresql"),
        ("postgresql+psycopg://u:secret@127.0.0.1:11000/db", "postgresql+psycopg"),
        ("postgres://u:secret@127.0.0.1:11000/db", "postgres"),
    ],
)
def test_entrypoint_refuses_a_non_psycopg2_storage_url(url: str, scheme: str) -> None:
    # T-322: on SQLAlchemy 2.1 these become psycopg 3 — runs cannot start while healthchecks
    # still pass. The service must die loudly instead, without echoing the password.
    result = _run_entrypoint(url)
    assert result.returncode == 64
    assert result.stdout == ""
    assert f"scheme '{scheme}'" in result.stderr
    assert "secret" not in result.stderr
