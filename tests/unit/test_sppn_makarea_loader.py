from __future__ import annotations

import inspect
import zipfile
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders import sppn_makarea_loader

if TYPE_CHECKING:
    from pathlib import Path


def test_discover_sppn_makarea_zip_source(tmp_path: Path) -> None:
    archive = tmp_path / "구역의도형_전체분_세종특별자치시.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        for suffix in (".shp", ".shx", ".dbf"):
            zip_file.writestr(f"36110/TL_SPPN_MAKAREA{suffix}", b"placeholder")

    sources = sppn_makarea_loader.discover_sppn_makarea_sources(archive)

    assert len(sources) == 1
    assert sources[0].source_file == (
        "구역의도형_전체분_세종특별자치시.zip:36110/TL_SPPN_MAKAREA.shp"
    )
    assert sources[0].zip_prefix == "36110/TL_SPPN_MAKAREA"


def test_discover_sppn_makarea_directory_sorts_zone_zips(tmp_path: Path) -> None:
    for name in (
        "구역의도형_전체분_경상남도.zip",
        "구역의도형_전체분_세종특별자치시.zip",
    ):
        with zipfile.ZipFile(tmp_path / name, "w") as zip_file:
            for suffix in (".shp", ".shx", ".dbf"):
                zip_file.writestr(f"36110/TL_SPPN_MAKAREA{suffix}", b"placeholder")

    sources = sppn_makarea_loader.discover_sppn_makarea_sources(tmp_path)

    assert [source.zip_path.name for source in sources if source.zip_path] == sorted(
        source.zip_path.name for source in sources if source.zip_path
    )


def test_discover_sppn_makarea_rejects_missing_layer(tmp_path: Path) -> None:
    archive = tmp_path / "zone.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("36110/TL_SCCO_SIG.shp", b"placeholder")

    with pytest.raises(LoaderError, match="expected one TL_SPPN_MAKAREA"):
        sppn_makarea_loader.discover_sppn_makarea_sources(archive)


def test_sppn_loader_sanitizes_stage_and_upserts_target() -> None:
    source = inspect.getsource(sppn_makarea_loader._insert_stage)

    assert sppn_makarea_loader._clean_sql("sig_cd::text") == (
        "NULLIF(BTRIM(sig_cd::text), '')"
    )
    assert "chr(0)" not in source
    assert "ST_Covers" not in source
    assert "ON CONFLICT (sig_cd, makarea_id) DO UPDATE" in source
    assert "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Force2D(geom)), 3))" in source


def test_sppn_loader_stage_table_is_advisory_locked() -> None:
    source = inspect.getsource(sppn_makarea_loader)

    assert "pg_try_advisory_lock(hashtext(:lock_key))" in source
    assert "pg_advisory_unlock(hashtext(:lock_key))" in source
    assert "another TL_SPPN_MAKAREA staging load is already running" in source


def test_sppn_loader_records_load_manifest_for_c10() -> None:
    source = inspect.getsource(sppn_makarea_loader._record_manifest)

    assert "INSERT INTO load_manifest" in source
    assert '"table_name": TARGET_TABLE' in source
    assert sppn_makarea_loader.TARGET_TABLE == "tl_sppn_makarea"
    assert '"kind": "sppn_makarea"' in source
    assert "CAST(:source_set AS jsonb)" in source
