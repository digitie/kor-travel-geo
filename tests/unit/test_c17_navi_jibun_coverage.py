from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kortravelgeo.loaders.augment_harness import JoinKey, KeyOverlapMeasurement
from kortravelgeo.loaders.c17_navi_jibun_coverage import (
    C17NaviJibunCoverageComparison,
    C17NaviJibunCoverageResult,
    NaviJibunMembers,
    build_c17_navi_jibun_coverage_report,
    discover_navi_jibun_members,
    iter_navi_jibun_rows,
    key_coverage_sample_sql,
    parse_navi_jibun_row,
)
from kortravelgeo.loaders.text.common import TextSource


def test_discover_navi_jibun_members_from_directory(tmp_path: Path) -> None:
    (tmp_path / "match_jibun_sejong.txt").write_bytes((_NAVI_JIBUN_SAMPLE + "\n").encode("cp949"))
    (tmp_path / "match_build_sejong.txt").write_text("ignored\n", encoding="utf-8")

    members = discover_navi_jibun_members(tmp_path)

    assert [source.name for source in members.match_jibun] == ["match_jibun_sejong.txt"]
    assert members.counts == {"match_jibun_members": 1, "match_jibun_present": 1}


def test_discover_navi_jibun_members_from_zip(tmp_path: Path) -> None:
    archive = tmp_path / "navi.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("match_jibun_seoul.txt", (_NAVI_JIBUN_SAMPLE + "\n").encode("cp949"))
        zip_file.writestr("match_rs_entrc.txt", b"ignored\n")

    members = discover_navi_jibun_members(archive)

    assert [source.name for source in members.match_jibun] == ["match_jibun_seoul.txt"]


def test_parse_navi_jibun_row_extracts_parcel_and_road_keys() -> None:
    row = parse_navi_jibun_row(
        _pipe(_NAVI_JIBUN_SAMPLE),
        source_name="match_jibun_sejong.txt",
        line_no=1,
        source_yyyymm="202604",
    )

    assert row.bjd_cd == "3611035026"
    assert row.pnu == "3611035026101770004"
    assert row.rncode_full == "361101000015"
    assert row.sig_cd == "36110"
    assert row.rn_cd == "1000015"
    assert row.buld_se_cd == "0"
    assert row.buld_mnnm == 74
    assert row.buld_slno == 0
    assert row.bd_mgt_sn == "3611035026101770004000001"
    assert row.adm_cd == "3611035000"
    assert row.source_yyyymm == "202604"


def test_iter_navi_jibun_rows_reads_cp949_text(tmp_path: Path) -> None:
    source = tmp_path / "match_jibun_sejong.txt"
    source.write_bytes((_NAVI_JIBUN_SAMPLE + "\n").encode("cp949"))

    rows = tuple(iter_navi_jibun_rows(tmp_path, source_yyyymm="202604"))

    assert len(rows) == 1
    assert rows[0].source_file == "match_jibun_sejong.txt"
    assert rows[0].pnu == "3611035026101770004"


def test_key_coverage_sample_sql_uses_except_without_serving_writes() -> None:
    sql = key_coverage_sample_sql(
        "_ktg_c17_navi_jibun",
        "tl_juso_parcel_link",
        (JoinKey("bd_mgt_sn", "bd_mgt_sn"), JoinKey("pnu", "pnu")),
    )

    assert 'FROM "_ktg_c17_navi_jibun" l' in sql
    assert 'FROM "tl_juso_parcel_link" r' in sql
    assert "EXCEPT" in sql
    assert "left_only" in sql
    assert "right_only" in sql
    assert "INSERT INTO" not in sql
    assert "CREATE MATERIALIZED VIEW" not in sql


def test_c17_metrics_keep_navi_jibun_validation_only() -> None:
    comparison = C17NaviJibunCoverageResult(
        navi_path="202604_내비게이션용DB_전체분",
        source_yyyymm="202604",
        members=NaviJibunMembers(match_jibun=(_source("match_jibun_sejong.txt"),)),
        staging_rows=1,
        comparisons=(
            C17NaviJibunCoverageComparison(
                name="navi_jibun_to_tl_juso_parcel_link_bd_pnu",
                left_source="navi_full.match_jibun_*.txt",
                right_source="tl_juso_parcel_link",
                key_contract="bd_mgt_sn_pnu",
                join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"), JoinKey("pnu", "pnu")),
                overlap=KeyOverlapMeasurement(1, 2, 1, 2, 1, 0, 1),
                sample=({"sample_kind": "right_only", "keys": {"pnu": "P"}},),
            ),
        ),
    )

    metrics = comparison.metrics()

    assert metrics["source_category"] == "navi_full"
    assert metrics["member_key"] == "navi_full.match_jibun"
    assert metrics["coordinate_load"] is False
    assert metrics["serving_promotion"] is False
    assert metrics["staging_rows"] == {"navi_match_jibun": 1}
    assert metrics["comparisons"]["navi_jibun_to_tl_juso_parcel_link_bd_pnu"][
        "key_overlap"
    ]["right_only_count"] == 1
    assert comparison.sample() == (
        {
            "comparison": "navi_jibun_to_tl_juso_parcel_link_bd_pnu",
            "sample_kind": "right_only",
            "keys": {"pnu": "P"},
        },
    )


@pytest.mark.asyncio
async def test_build_c17_report_skips_when_match_jibun_absent(tmp_path: Path) -> None:
    class DummyEngine:
        pass

    report = await build_c17_navi_jibun_coverage_report(
        DummyEngine(),  # type: ignore[arg-type]
        tmp_path,
        source_yyyymm="202604",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-117"
    assert report.generated_at == "2026-06-14T00:00:00+00:00"
    assert report.skipped_count == 1
    assert report.groups[0].status == "skipped"
    assert report.groups[0].metrics["source_members"] == {
        "match_jibun_members": 0,
        "match_jibun_present": 0,
    }


_NAVI_JIBUN_SAMPLE = (
    "3611035026|세종특별자치시||장군면|하봉리|0|177|4|361101000015|0|74|0|0|"
    "Sejong-si||Janggun-myeon|Habong-ri||3611035026101770004000001|3611035000"
)


def _source(name: str) -> TextSource:
    return TextSource(path=Path(name), name=name, size=1)


def _pipe(value: str) -> list[str]:
    return value.split("|")
