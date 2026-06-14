from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c17_navi_jibun_coverage import (
    compare_c17_navi_jibun_coverage,
    drop_c17_navi_jibun_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c17_navi_jibun_coverage_sample_when_enabled(
    tmp_path: Path,
) -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C17 real-data PostGIS smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a database with serving tables")

    navi_path = _require_navi_match_jibun_source(tmp_path)
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("SELECT to_regclass('public.tl_juso_parcel_link')"))
            if exists is None:
                pytest.skip("tl_juso_parcel_link is not available")

        comparison = await compare_c17_navi_jibun_coverage(
            engine,
            navi_path,
            source_yyyymm="202604",
            limit_per_member=2,
            sample_limit=2,
        )

        metrics = comparison.metrics()
        assert comparison.staging_rows == 2
        assert metrics["coordinate_load"] is False
        assert metrics["serving_promotion"] is False
        assert metrics["source_members"] == {
            "match_jibun_members": 1,
            "match_jibun_present": 1,
        }
        assert len(comparison.comparisons) == 2
    finally:
        await drop_c17_navi_jibun_staging_tables(engine)
        await engine.dispose()


def _require_navi_match_jibun_source(tmp_path: Path) -> Path:
    for root in DATA_ROOTS:
        if not root.exists():
            continue
        for candidate in (
            root / "202604_내비게이션용DB_전체분",
            root / "내비게이션용DB",
        ):
            if candidate.exists() and any(candidate.glob("match_jibun_*.txt")):
                return candidate
        archive = root / "202604_내비게이션용DB_전체분.7z"
        if archive.exists():
            extracted = tmp_path / "navi"
            extracted.mkdir()
            _extract_one_match_jibun_member(archive, extracted / "match_jibun_sejong.txt")
            return extracted
    pytest.skip("actual navi match_jibun data not available for C17 optional smoke")


def _extract_one_match_jibun_member(archive: Path, dest: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if seven_zip is None:
        pytest.skip("7z command not available to materialize navi match_jibun sample")
    proc = subprocess.run(
        [seven_zip, "x", "-so", str(archive), "match_jibun_sejong.txt"],
        check=True,
        capture_output=True,
    )
    dest.write_bytes(proc.stdout)
