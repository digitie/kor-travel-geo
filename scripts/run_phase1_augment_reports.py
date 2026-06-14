"""T-121 phase-1 nationwide augmentation report runner.

이 스크립트는 운영 CLI가 아니라 C11~C17 prototype을 실제 전국 원천에 대해
한 번에 실행하고 JSON/Markdown artifact를 남기는 계측 도구다. 각 prototype의
serving 편입 여부는 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.augment_harness import (
    SIDO_NAMES,
    AugmentReport,
)
from kortravelgeo.loaders.c11_entrance_sources import (
    build_c11_entrance_report,
    discover_c11_entrance_source_groups,
    drop_c11_entrance_staging_tables,
)
from kortravelgeo.loaders.c12_connection_lines import (
    build_c12_connection_report,
    discover_c12_connection_source_groups,
    drop_c12_connection_staging_tables,
)
from kortravelgeo.loaders.c13_detail_dong import (
    build_c13_detail_dong_report,
    discover_c13_detail_dong_source_groups,
    drop_c13_detail_dong_staging_tables,
)
from kortravelgeo.loaders.c14_national_point_grid import build_c14_national_point_grid_report
from kortravelgeo.loaders.c15_civil_service_poi import (
    build_c15_civil_service_poi_report,
    drop_c15_civil_service_poi_staging_tables,
)
from kortravelgeo.loaders.c16_address_building_drift import (
    build_c16_address_building_drift_report,
    drop_c16_address_building_staging_tables,
)
from kortravelgeo.loaders.c17_navi_jibun_coverage import (
    build_c17_navi_jibun_coverage_report,
    drop_c17_navi_jibun_staging_tables,
)
from kortravelgeo.settings import get_settings

CaseId = Literal["C11", "C12", "C13", "C14", "C15", "C16", "C17"]
ALL_CASES: tuple[CaseId, ...] = ("C11", "C12", "C13", "C14", "C15", "C16", "C17")
RUN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SourceInput:
    key: str
    path: str
    source_yyyymm: str | None
    materialized_from: str | None = None


@dataclass(frozen=True, slots=True)
class CaseRun:
    case_id: CaseId
    task_id: str
    output_path: str
    seconds: float
    report_summary: Mapping[str, object]
    sources: tuple[SourceInput, ...]


@dataclass(frozen=True, slots=True)
class RunSummary:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    total_seconds: float
    data_root: str
    output_dir: str
    git_commit: str | None
    git_branch: str | None
    cases: tuple[CaseRun, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run C11-C17 phase-1 augmentation reports against real source data.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/juso"),
        help="도로명주소 실제 원천 root. 기본값은 data/juso.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact output directory. 기본값은 artifacts/augment/t121-phase1-<run-id>.",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=ALL_CASES,
        dest="cases",
        help="실행할 case. 여러 번 지정 가능하며 생략하면 C11~C17 전체를 실행한다.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        help="C11~C13에서 실행할 시도명. 여러 번 지정 가능하며 생략하면 17개 시도 전체.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. 생략하면 KTG_PG_DSN/.env를 사용한다.")
    parser.add_argument(
        "--pg-statement-timeout-ms",
        type=int,
        default=600_000,
        help="리포트 측정용 PostgreSQL statement_timeout. 기본값은 600000ms.",
    )
    parser.add_argument("--sample-limit", type=int, default=20, help="각 metric sample 개수.")
    parser.add_argument("--c12-tolerance-m", type=float, default=1.0)
    parser.add_argument("--c15-outlier-threshold-m", type=float, default=100.0)
    parser.add_argument(
        "--c14-row-limit-per-layer",
        type=int,
        help="C14 smoke용 layer별 행 제한. 전국 실행에서는 생략한다.",
    )
    parser.add_argument(
        "--c14-center-row-limit",
        type=int,
        help="C14 smoke용 중심점 행 제한. 전국 실행에서는 생략한다.",
    )
    parser.add_argument(
        "--c15-row-limit",
        type=int,
        help="C15 smoke용 민원행정기관 행 제한. 전국 실행에서는 생략한다.",
    )
    parser.add_argument(
        "--c16-limit-per-member",
        type=int,
        help="C16 smoke용 text member별 행 제한. 전국 실행에서는 생략한다.",
    )
    parser.add_argument(
        "--c17-limit-per-member",
        type=int,
        help="C17 smoke용 text member별 행 제한. 전국 실행에서는 생략한다.",
    )
    parser.add_argument(
        "--materialize-electronic-map",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="전자지도 시도별 ZIP을 output 아래에 풀어 C11/C12 입력 디렉터리로 사용한다.",
    )
    parser.add_argument(
        "--materialize-navi-7z",
        action="store_true",
        help="C17 입력이 .7z뿐이면 output 아래에 match_jibun_*.txt를 materialize한다.",
    )
    parser.add_argument(
        "--git-repo",
        type=Path,
        help="Git metadata를 기록할 repo path. WSL 미러에서는 F:/dev/... NTFS 경로 권장.",
    )
    return parser


async def run_phase1_reports(
    *,
    data_root: Path,
    output_dir: Path,
    cases: Sequence[CaseId] = ALL_CASES,
    sido_names: Sequence[str] | None = None,
    engine: AsyncEngine,
    sample_limit: int = 20,
    c12_tolerance_m: float = 1.0,
    c15_outlier_threshold_m: float = 100.0,
    c14_row_limit_per_layer: int | None = None,
    c14_center_row_limit: int | None = None,
    c15_row_limit: int | None = None,
    c16_limit_per_member: int | None = None,
    c17_limit_per_member: int | None = None,
    materialize_electronic_map: bool = True,
    materialize_navi_7z: bool = False,
    git_repo: Path | None = None,
) -> RunSummary:
    started = datetime.now(UTC)
    start_clock = time.perf_counter()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    ensure_output_dir(output_dir)
    selected_sidos = tuple(sido_names or SIDO_NAMES)
    source_plan = build_source_plan(
        data_root,
        output_dir=output_dir,
        sido_names=selected_sidos,
        materialize_electronic_map=materialize_electronic_map,
        materialize_navi_7z=materialize_navi_7z,
    )
    case_runs: list[CaseRun] = []
    for case_id in cases:
        print(f"[{case_id}] 시작", flush=True)
        case_started = time.perf_counter()
        report = await run_phase1_case(
            case_id,
            engine=engine,
            source_plan=source_plan,
            sido_names=selected_sidos,
            sample_limit=sample_limit,
            c12_tolerance_m=c12_tolerance_m,
            c15_outlier_threshold_m=c15_outlier_threshold_m,
            c14_row_limit_per_layer=c14_row_limit_per_layer,
            c14_center_row_limit=c14_center_row_limit,
            c15_row_limit=c15_row_limit,
            c16_limit_per_member=c16_limit_per_member,
            c17_limit_per_member=c17_limit_per_member,
        )
        seconds = time.perf_counter() - case_started
        output_path = output_dir / f"{case_id.lower()}-{report.task_id.lower()}.json"
        write_report_json(report, output_path)
        case_run = CaseRun(
            case_id=case_id,
            task_id=report.task_id,
            output_path=str(output_path),
            seconds=round(seconds, 3),
            report_summary=report.summary(),
            sources=source_plan.case_sources(case_id),
        )
        case_runs.append(case_run)
        print(f"[{case_id}] 완료: {case_run.report_summary}", flush=True)
    finished = datetime.now(UTC)
    summary = RunSummary(
        schema_version=RUN_SCHEMA_VERSION,
        run_id=run_id,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        total_seconds=round(time.perf_counter() - start_clock, 3),
        data_root=str(data_root),
        output_dir=str(output_dir),
        git_commit=_git_value(git_repo, "rev-parse", "HEAD"),
        git_branch=_git_value(git_repo, "branch", "--show-current"),
        cases=tuple(case_runs),
    )
    write_summary(summary, output_dir)
    return summary


def build_source_plan(
    data_root: Path,
    *,
    output_dir: Path,
    sido_names: Sequence[str] = SIDO_NAMES,
    materialize_electronic_map: bool,
    materialize_navi_7z: bool,
) -> SourcePlan:
    root = data_root.resolve()
    materialized_root = output_dir / "materialized"
    electronic_root = root / "도로명주소 전자지도" / "202604"
    if materialize_electronic_map:
        electronic_root = materialize_electronic_map_zips(
            electronic_root,
            materialized_root,
            sido_names=sido_names,
        )
    navi_path, navi_materialized_from = resolve_navi_path(
        root,
        materialized_root=materialized_root,
        materialize_7z=materialize_navi_7z,
    )
    detail_address_zip = latest_existing(
        root / "202605_상세주소DB_전체분.zip",
        root / "202604_상세주소DB_전체분.zip",
    )
    return SourcePlan(
        c11_bundle_root=root / "도로명주소 건물 도형" / "202604",
        c11_bundle_yyyymm="202604",
        electronic_map_root=electronic_root,
        electronic_map_yyyymm="202604",
        c13_detail_dong_root=root / "건물군 내 상세주소 동 도형" / "202604",
        c13_detail_dong_yyyymm="202604",
        c13_detail_address_zip=detail_address_zip,
        c13_detail_address_yyyymm=yyyymm_from_path(detail_address_zip) or "unknown",
        c14_grid_shape_zip=root / "국가지점번호 도형" / "202405" / "국가지점번호도형_5월분.zip",
        c14_grid_center_zip=(
            root / "국가지점번호 중심점" / "202405" / "국가지점번호중심점_5월분.zip"
        ),
        c14_yyyymm="202405",
        c15_civil_service_zip=root / "민원행정기관전자지도_240124.zip",
        c15_yyyymm="202401",
        c16_address_db_zip=root / "202605_주소DB_전체분.zip",
        c16_building_db_zip=root / "202605_건물DB_전체분.zip",
        c16_yyyymm="202605",
        c17_navi_path=navi_path,
        c17_navi_yyyymm="202604",
        c17_navi_materialized_from=navi_materialized_from,
    )


@dataclass(frozen=True, slots=True)
class SourcePlan:
    c11_bundle_root: Path
    c11_bundle_yyyymm: str
    electronic_map_root: Path
    electronic_map_yyyymm: str
    c13_detail_dong_root: Path
    c13_detail_dong_yyyymm: str
    c13_detail_address_zip: Path
    c13_detail_address_yyyymm: str
    c14_grid_shape_zip: Path
    c14_grid_center_zip: Path
    c14_yyyymm: str
    c15_civil_service_zip: Path
    c15_yyyymm: str
    c16_address_db_zip: Path
    c16_building_db_zip: Path
    c16_yyyymm: str
    c17_navi_path: Path
    c17_navi_yyyymm: str
    c17_navi_materialized_from: str | None = None

    def source_yyyymm(self, case_id: CaseId) -> str:
        if case_id in {"C11", "C12"}:
            return (
                f"bundle={self.c11_bundle_yyyymm}; "
                f"electronic={self.electronic_map_yyyymm}"
            )
        if case_id == "C13":
            return (
                f"detail_dong={self.c13_detail_dong_yyyymm}; "
                f"detail_address_db={self.c13_detail_address_yyyymm}"
            )
        if case_id == "C14":
            return self.c14_yyyymm
        if case_id == "C15":
            return self.c15_yyyymm
        if case_id == "C16":
            return f"address_db={self.c16_yyyymm}; building_db={self.c16_yyyymm}"
        return self.c17_navi_yyyymm

    def case_sources(self, case_id: CaseId) -> tuple[SourceInput, ...]:
        if case_id in {"C11", "C12"}:
            return (
                SourceInput(
                    "building_shape_bundle",
                    str(self.c11_bundle_root),
                    self.c11_bundle_yyyymm,
                ),
                SourceInput(
                    "electronic_map",
                    str(self.electronic_map_root),
                    self.electronic_map_yyyymm,
                ),
            )
        if case_id == "C13":
            return (
                SourceInput(
                    "detail_dong",
                    str(self.c13_detail_dong_root),
                    self.c13_detail_dong_yyyymm,
                ),
                SourceInput(
                    "detail_address_db",
                    str(self.c13_detail_address_zip),
                    self.c13_detail_address_yyyymm,
                ),
            )
        if case_id == "C14":
            return (
                SourceInput(
                    "national_point_grid_shape",
                    str(self.c14_grid_shape_zip),
                    self.c14_yyyymm,
                ),
                SourceInput(
                    "national_point_grid_center",
                    str(self.c14_grid_center_zip),
                    self.c14_yyyymm,
                ),
            )
        if case_id == "C15":
            return (
                SourceInput(
                    "civil_service_institution_map",
                    str(self.c15_civil_service_zip),
                    self.c15_yyyymm,
                ),
            )
        if case_id == "C16":
            return (
                SourceInput("address_db_full", str(self.c16_address_db_zip), self.c16_yyyymm),
                SourceInput("building_db_full", str(self.c16_building_db_zip), self.c16_yyyymm),
            )
        return (
            SourceInput(
                "navi_full.match_jibun",
                str(self.c17_navi_path),
                self.c17_navi_yyyymm,
                self.c17_navi_materialized_from,
            ),
        )


async def run_phase1_case(
    case_id: CaseId,
    *,
    engine: AsyncEngine,
    source_plan: SourcePlan,
    sido_names: Sequence[str],
    sample_limit: int,
    c12_tolerance_m: float,
    c15_outlier_threshold_m: float,
    c14_row_limit_per_layer: int | None,
    c14_center_row_limit: int | None,
    c15_row_limit: int | None,
    c16_limit_per_member: int | None,
    c17_limit_per_member: int | None,
) -> AugmentReport:
    if case_id == "C11":
        groups = discover_c11_entrance_source_groups(
            bundle_root=source_plan.c11_bundle_root,
            electronic_map_root=source_plan.electronic_map_root,
            sido_names=sido_names,
        )
        try:
            return await build_c11_entrance_report(
                engine,
                groups,
                source_yyyymm=source_plan.source_yyyymm(case_id),
                sample_limit=sample_limit,
            )
        finally:
            await drop_c11_entrance_staging_tables(engine)
    if case_id == "C12":
        groups = discover_c12_connection_source_groups(
            bundle_root=source_plan.c11_bundle_root,
            electronic_map_root=source_plan.electronic_map_root,
            sido_names=sido_names,
        )
        try:
            return await build_c12_connection_report(
                engine,
                groups,
                source_yyyymm=source_plan.source_yyyymm(case_id),
                sample_limit=sample_limit,
                tolerance_m=c12_tolerance_m,
            )
        finally:
            await drop_c12_connection_staging_tables(engine)
    if case_id == "C13":
        groups = discover_c13_detail_dong_source_groups(
            detail_dong_root=source_plan.c13_detail_dong_root,
            detail_address_db_zip=source_plan.c13_detail_address_zip,
            sido_names=sido_names,
        )
        try:
            return await build_c13_detail_dong_report(
                engine,
                groups,
                source_yyyymm=source_plan.source_yyyymm(case_id),
                sample_limit=sample_limit,
            )
        finally:
            await drop_c13_detail_dong_staging_tables(engine)
    if case_id == "C14":
        return build_c14_national_point_grid_report(
            source_plan.c14_grid_shape_zip,
            source_plan.c14_grid_center_zip,
            source_yyyymm=source_plan.source_yyyymm(case_id),
            row_limit_per_layer=c14_row_limit_per_layer,
            center_row_limit=c14_center_row_limit,
            sample_limit=sample_limit,
        )
    if case_id == "C15":
        try:
            return await build_c15_civil_service_poi_report(
                engine,
                source_plan.c15_civil_service_zip,
                source_yyyymm=source_plan.source_yyyymm(case_id),
                sample_limit=sample_limit,
                outlier_threshold_m=c15_outlier_threshold_m,
                row_limit=c15_row_limit,
        )
        finally:
            await drop_c15_civil_service_poi_staging_tables(engine)
    if case_id == "C16":
        try:
            return await build_c16_address_building_drift_report(
                engine,
                source_plan.c16_address_db_zip,
                source_plan.c16_building_db_zip,
                source_yyyymm=source_plan.source_yyyymm(case_id),
                sample_limit=sample_limit,
                limit_per_member=c16_limit_per_member,
        )
        finally:
            await drop_c16_address_building_staging_tables(engine)
    try:
        return await build_c17_navi_jibun_coverage_report(
            engine,
            source_plan.c17_navi_path,
            source_yyyymm=source_plan.source_yyyymm(case_id),
            sample_limit=sample_limit,
            limit_per_member=c17_limit_per_member,
        )
    finally:
        await drop_c17_navi_jibun_staging_tables(engine)


def materialize_electronic_map_zips(
    electronic_zip_root: Path,
    materialized_root: Path,
    *,
    sido_names: Sequence[str] = SIDO_NAMES,
) -> Path:
    target_root = materialized_root / "electronic_map_202604"
    target_root.mkdir(parents=True, exist_ok=True)
    for sido_name in sido_names:
        archive = electronic_zip_root / f"{sido_name}.zip"
        if not archive.exists():
            continue
        target = target_root / archive.stem
        marker = target / ".ktg-materialized-ok"
        if marker.exists():
            continue
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(target)
        marker.write_text(archive.name + "\n", encoding="utf-8")
    return target_root


def resolve_navi_path(
    data_root: Path,
    *,
    materialized_root: Path,
    materialize_7z: bool,
) -> tuple[Path, str | None]:
    for candidate in (
        data_root / "202604_내비게이션용DB_전체분",
        data_root / "내비게이션용DB",
    ):
        if candidate.exists():
            return candidate, None
    archive = data_root / "202604_내비게이션용DB_전체분.7z"
    if not archive.exists() or not materialize_7z:
        return archive, None
    target = materialized_root / "navi_match_jibun_202604"
    marker = target / ".ktg-materialized-ok"
    if not marker.exists():
        target.mkdir(parents=True, exist_ok=True)
        materialize_navi_match_jibun(archive, target)
        marker.write_text(str(archive) + "\n", encoding="utf-8")
    return target, str(archive)


def materialize_navi_match_jibun(archive: Path, target_dir: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if seven_zip is None:
        msg = "7z/7zz/7za command not found; cannot materialize navi .7z"
        raise RuntimeError(msg)
    listing = subprocess.run(
        [seven_zip, "l", "-ba", str(archive)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    members = sorted(
        line.rsplit(maxsplit=1)[-1]
        for line in listing.stdout.splitlines()
        if "match_jibun_" in line and line.rstrip().endswith(".txt")
    )
    if not members:
        msg = f"match_jibun_*.txt member not found in {archive}"
        raise RuntimeError(msg)
    for member in members:
        with (target_dir / Path(member).name).open("wb") as file:
            subprocess.run(
                [seven_zip, "x", "-so", str(archive), member],
                check=True,
                stdout=file,
            )


def latest_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def yyyymm_from_path(path: Path) -> str | None:
    for part in (path.name, *path.parts[::-1]):
        token = part[:6]
        if len(token) == 6 and token.isdigit():
            return token
    return None


def write_report_json(report: AugmentReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary(summary: RunSummary, output_dir: Path) -> None:
    payload = json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n"
    (output_dir / "summary.json").write_text(payload, encoding="utf-8")
    (output_dir / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")


def summary_markdown(summary: RunSummary) -> str:
    lines = [
        "# T-121 phase 1 전국 보강 리포트",
        "",
        f"- run_id: `{summary.run_id}`",
        f"- data_root: `{summary.data_root}`",
        f"- git_commit: `{summary.git_commit or 'unknown'}`",
        f"- total_seconds: `{summary.total_seconds}`",
        "",
        "| case | task | used | skipped | failed | seconds | artifact |",
        "|------|------|------|---------|--------|---------|----------|",
    ]
    for case_run in summary.cases:
        report_summary = case_run.report_summary
        lines.append(
            "| "
            f"{case_run.case_id} | {case_run.task_id} | "
            f"{report_summary.get('used')} | {report_summary.get('skipped')} | "
            f"{report_summary.get('failed')} | {case_run.seconds} | "
            f"`{case_run.output_path}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _git_value(git_repo: Path | None, *args: str) -> str | None:
    if git_repo is None:
        return None
    for git_cmd in ("git.exe", "git"):
        proc = subprocess.run(
            [git_cmd, "-C", str(git_repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    return None


def _parse_cases(values: Iterable[str] | None) -> tuple[CaseId, ...]:
    if values is None:
        return ALL_CASES
    return cast("tuple[CaseId, ...]", tuple(values))


async def _main_async(args: argparse.Namespace) -> None:
    data_root = args.data_root
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("artifacts") / "augment" / f"t121-phase1-{run_id}"
    settings = get_settings()
    settings_update: dict[str, object] = {
        "pg_statement_timeout_ms": args.pg_statement_timeout_ms,
    }
    if args.pg_dsn:
        settings_update["pg_dsn"] = args.pg_dsn
    settings = settings.model_copy(update=settings_update)
    engine = make_async_engine(settings)
    try:
        await run_phase1_reports(
            data_root=data_root,
            output_dir=output_dir,
            cases=_parse_cases(args.cases),
            sido_names=tuple(args.sido) if args.sido else None,
            engine=engine,
            sample_limit=args.sample_limit,
            c12_tolerance_m=args.c12_tolerance_m,
            c15_outlier_threshold_m=args.c15_outlier_threshold_m,
            c14_row_limit_per_layer=args.c14_row_limit_per_layer,
            c14_center_row_limit=args.c14_center_row_limit,
            c15_row_limit=args.c15_row_limit,
            c16_limit_per_member=args.c16_limit_per_member,
            c17_limit_per_member=args.c17_limit_per_member,
            materialize_electronic_map=args.materialize_electronic_map,
            materialize_navi_7z=args.materialize_navi_7z,
            git_repo=args.git_repo,
        )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
