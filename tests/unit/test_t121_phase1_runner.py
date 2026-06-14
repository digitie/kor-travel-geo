from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.run_phase1_augment_reports import (
    CaseRun,
    RunSummary,
    SourceInput,
    build_parser,
    build_source_plan,
    latest_existing,
    summary_markdown,
    write_summary,
)


def test_t121_runner_parser_accepts_case_and_limits() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--case",
            "C11",
            "--case",
            "C17",
            "--sido",
            "세종특별자치시",
            "--sample-limit",
            "3",
            "--pg-statement-timeout-ms",
            "120000",
            "--c16-limit-per-member",
            "2",
            "--materialize-navi-7z",
            "--git-repo",
            "F:/dev/kor-travel-geo-codex",
        ]
    )

    assert args.cases == ["C11", "C17"]
    assert args.sido == ["세종특별자치시"]
    assert args.sample_limit == 3
    assert args.pg_statement_timeout_ms == 120000
    assert args.c16_limit_per_member == 2
    assert args.materialize_electronic_map is True
    assert args.materialize_navi_7z is True
    assert args.git_repo.as_posix() == "F:/dev/kor-travel-geo-codex"


def test_build_source_plan_materializes_electronic_map_zip(tmp_path: Path) -> None:
    data_root = tmp_path / "juso"
    electronic_zip_root = data_root / "도로명주소 전자지도" / "202604"
    electronic_zip_root.mkdir(parents=True)
    with zipfile.ZipFile(electronic_zip_root / "세종특별자치시.zip", "w") as zip_file:
        zip_file.writestr("36000/TL_SPBD_BULD.shp", b"shape")
    (data_root / "도로명주소 건물 도형" / "202604").mkdir(parents=True)
    (data_root / "건물군 내 상세주소 동 도형" / "202604").mkdir(parents=True)
    (data_root / "202604_상세주소DB_전체분.zip").write_bytes(b"zip")
    (data_root / "202604_내비게이션용DB_전체분.7z").write_bytes(b"7z")
    (data_root / "국가지점번호 도형" / "202405").mkdir(parents=True)
    (data_root / "국가지점번호 중심점" / "202405").mkdir(parents=True)

    plan = build_source_plan(
        data_root,
        output_dir=tmp_path / "out",
        materialize_electronic_map=True,
        materialize_navi_7z=False,
    )

    assert (plan.electronic_map_root / "세종특별자치시" / "36000" / "TL_SPBD_BULD.shp").is_file()
    assert plan.c13_detail_address_zip == data_root / "202604_상세주소DB_전체분.zip"
    assert plan.source_yyyymm("C11") == "bundle=202604; electronic=202604"
    assert plan.source_yyyymm("C13") == "detail_dong=202604; detail_address_db=202604"
    assert plan.case_sources("C17") == (
        SourceInput(
            "navi_full.match_jibun",
            str(data_root.resolve() / "202604_내비게이션용DB_전체분.7z"),
            "202604",
            None,
        ),
    )


def test_latest_existing_prefers_first_present(tmp_path: Path) -> None:
    older = tmp_path / "202604.zip"
    newer = tmp_path / "202605.zip"
    older.write_text("old", encoding="utf-8")

    assert latest_existing(newer, older) == older

    newer.write_text("new", encoding="utf-8")
    assert latest_existing(newer, older) == newer


def test_write_summary_outputs_json_and_markdown(tmp_path: Path) -> None:
    summary = RunSummary(
        schema_version=1,
        run_id="20260614T000000Z",
        started_at="2026-06-14T00:00:00+00:00",
        finished_at="2026-06-14T00:00:01+00:00",
        total_seconds=1.0,
        data_root="/data/juso",
        output_dir=str(tmp_path),
        git_commit="abc123",
        git_branch="agent/codex-t121",
        cases=(
            CaseRun(
                case_id="C11",
                task_id="T-111",
                output_path=str(tmp_path / "c11-t-111.json"),
                seconds=0.5,
                report_summary={
                    "task_id": "T-111",
                    "title": "C11",
                    "source_yyyymm": "bundle=202604; electronic=202604",
                    "used": 17,
                    "skipped": 0,
                    "failed": 0,
                    "total": 17,
                },
                sources=(SourceInput("electronic_map", "/data/electronic", "202604"),),
            ),
        ),
    )

    write_summary(summary, tmp_path)
    payload = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert payload["schema_version"] == 1
    assert payload["cases"][0]["sources"][0]["key"] == "electronic_map"
    assert "| C11 | T-111 | 17 | 0 | 0 | 0.5 |" in markdown
    assert summary_markdown(summary).startswith("# T-121 phase 1 전국 보강 리포트")
