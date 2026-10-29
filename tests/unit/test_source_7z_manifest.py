"""내비게이션 7z 원본의 확장자 없는 저장·검증 회귀."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.infra.source_member_scan import scan_part_manifest

if TYPE_CHECKING:
    from pathlib import Path


def test_7z_member_scan_uses_signature_when_storage_name_has_no_extension(tmp_path: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    if seven_zip is None:
        pytest.skip("7z 실행 파일이 필요합니다")
    (tmp_path / "match_build_seoul.txt").write_text("sample", encoding="utf-8")
    (tmp_path / "match_rs_entrc.txt").write_text("sample", encoding="utf-8")
    (tmp_path / "match_directory.txt").mkdir()
    archive = tmp_path / "input.7z"
    subprocess.run(
        [
            seven_zip,
            "a",
            str(archive),
            "match_build_seoul.txt",
            "match_rs_entrc.txt",
            "match_directory.txt",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    stored = archive.rename(tmp_path / "archive")
    manifest = scan_part_manifest(stored, part_key="archive")
    assert set(manifest.filenames()) == {"match_build_seoul.txt", "match_rs_entrc.txt"}
