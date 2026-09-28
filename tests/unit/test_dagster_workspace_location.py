from __future__ import annotations

import re
from pathlib import Path

from kortravelgeo.settings import Settings

_WORKSPACE = Path("kor-travel-geo-dagster/docker/workspace.yaml")


def test_workspace_location_name_matches_api_launch_selector() -> None:
    """geo-api launches Dagster runs with ``dagster_repository_location_name``; the
    webserver/daemon workspace must expose the code location under that same name or every
    ``launchRun`` fails with ``PipelineNotFoundError`` (T-307 regression, fixed in T-308)."""

    names = re.findall(
        r"^\s*location_name:\s*(\S+)\s*$",
        _WORKSPACE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )

    assert names == [Settings.model_fields["dagster_repository_location_name"].default]
