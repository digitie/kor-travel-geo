#!/usr/bin/env python3
"""T-213 proper live source-pipeline runner.

전국 실 원천 archive를 T-109 신규 source registry 경로로 등록하고,
`serving_recommended` match set을 rebuild-db batch DAG에 태운다. 실제 DB를
full load/MV swap 대상으로 삼는 destructive runner이므로 execute 모드에서는
typed confirmation을 요구한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

from kortravelgeo.api import _jobs
from kortravelgeo.api.app import _register_default_handlers
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.source_categories import SIDO_PARTS, category_by_code
from kortravelgeo.core.source_validation import GroupValidation, validate_group_manifest
from kortravelgeo.dto.source import (
    SourceMatchSetCreateRequest,
    SourceMatchSetItemRequest,
    UploadSessionCreateRequest,
)
from kortravelgeo.exceptions import ConflictError
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.rustfs import RustfsClient, require_enabled_rustfs, sha256_file
from kortravelgeo.infra.source_group_service import RegisterContext, SourceGroupRegistrar
from kortravelgeo.infra.source_match_set_service import SourceMatchSetRepository
from kortravelgeo.infra.source_member_scan import scan_group_manifest
from kortravelgeo.infra.source_upload_repo import SourceUploadSessionRepository
from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

RunProfile = Literal["serving_minimal", "serving_recommended"]

RUN_MARKER = "t213-live-proper"
ACTOR = RUN_MARKER
ROW_COUNT_TABLES = (
    "tl_juso_text",
    "tl_locsum_entrc",
    "tl_navi_building",
    "tl_navi_entrance",
    "tl_spbd_buld_polygon",
    "tl_roadaddr_entrc",
    "tl_sppn_makarea",
    "mv_geocode_target",
    "mv_geocode_text_search",
)


@dataclass(frozen=True, slots=True)
class SourcePart:
    part_key: str
    part_kind: str
    part_label: str | None
    path: Path


@dataclass(frozen=True, slots=True)
class SourceSpec:
    category: str
    yyyymm: str
    role: str
    group_kind: str
    parts: tuple[SourcePart, ...]


@dataclass(frozen=True, slots=True)
class RegisteredGroup:
    spec: SourceSpec
    source_file_group_id: str
    group_sha256: str | None
    validation: GroupValidation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.getenv("KTG_JUSO_DATA_ROOT", _default_data_root())),
        help="도로명주소 실 원천 root. 기본값은 KTG_JUSO_DATA_ROOT 또는 로컬 data/juso.",
    )
    parser.add_argument(
        "--dsn",
        default=os.getenv("KTG_TEST_PG_DSN") or os.getenv("KTG_PG_DSN"),
        help="대상 PostgreSQL DSN. 기본 fallback은 없다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="artifact/staging 출력 디렉터리. 기본값은 artifacts/t213-live-<run-id>.",
    )
    parser.add_argument(
        "--profile",
        choices=("serving_minimal", "serving_recommended"),
        default="serving_recommended",
        help="match set profile. T-213 acceptance 기본값은 serving_recommended.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 RustFS 등록, DB load, MV swap을 수행한다. 생략하면 plan만 출력한다.",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="runbook이 active match set, load table, MV swap을 바꾸는 것을 명시적으로 허용한다.",
    )
    parser.add_argument(
        "--typed-confirmation",
        help="execute에 필요한 확인 문구. 형식: RUN-T213-LIVE <database>",
    )
    parser.add_argument(
        "--force-promotion",
        action="store_true",
        help="known consistency ERROR를 batch promotion gate에서 강제 승격한다.",
    )
    parser.add_argument(
        "--force-promotion-reason",
        help="--force-promotion 사용 시 snapshot/audit에 남길 사유.",
    )
    parser.add_argument(
        "--allow-existing-jobs",
        action="store_true",
        help="실행 전 queued/running load_jobs 존재를 허용한다.",
    )
    parser.add_argument(
        "--promote-active-match-set",
        action="store_true",
        help=(
            "성공 후 새 T-213 match set을 active로 남긴다. 생략하면 기존 active match set을 "
            "복구해 검증 실행이 운영 serving 구성을 영구 대체하지 않게 한다."
        ),
    )
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=0,
        help="batch 완료 대기 제한. 0이면 제한 없음.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=30.0,
        help="load_jobs 상태 polling 간격.",
    )
    return parser


def _default_data_root() -> str:
    candidates = (
        Path("data/juso"),
        Path("/mnt/f/dev/kor-travel-geo/data/juso"),
        Path("/home/digitie/kor-travel-geo-data/juso"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def build_source_specs(data_root: Path, profile: RunProfile) -> tuple[SourceSpec, ...]:
    root = data_root.expanduser().resolve()
    specs = [
        _single_spec(
            root,
            category="roadname_hangul_full",
            yyyymm="202605",
            path=root / "202605_도로명주소 한글_전체분.zip",
        ),
        _single_spec(
            root,
            category="locsum_full",
            yyyymm="202604",
            path=root / "202604_위치정보요약DB_전체분.zip",
        ),
        _single_spec(
            root,
            category="navi_full",
            yyyymm="202604",
            path=root / "202604_내비게이션용DB_전체분.7z",
        ),
        _multipart_spec(
            root,
            category="electronic_map_full",
            yyyymm="202604",
            directory=root / "도로명주소 전자지도" / "202604",
            filename=lambda sido_name: f"{sido_name}.zip",
        ),
    ]
    if profile == "serving_recommended":
        specs.extend(
            (
                _multipart_spec(
                    root,
                    category="roadaddr_entrance_full",
                    yyyymm="202604",
                    directory=root / "도로명주소 출입구 정보" / "202604",
                    filename=lambda sido_name: f"도로명주소출입구_전체분_{sido_name}.zip",
                ),
                _multipart_spec(
                    root,
                    category="zone_shape_full",
                    yyyymm="202603",
                    directory=root / "구역의도형" / "202603",
                    filename=lambda sido_name: f"구역의도형_전체분_{sido_name}.zip",
                ),
            )
        )
    missing = [str(part.path) for spec in specs for part in spec.parts if not part.path.exists()]
    if missing:
        joined = "\n  - ".join(missing)
        raise SystemExit(f"필수 원천 파일이 없습니다:\n  - {joined}")
    return tuple(specs)


def _single_spec(
    data_root: Path,
    *,
    category: str,
    yyyymm: str,
    path: Path,
) -> SourceSpec:
    del data_root
    catalog = category_by_code[category]
    return SourceSpec(
        category=category,
        yyyymm=yyyymm,
        role=catalog.default_role,
        group_kind=catalog.group_kind,
        parts=(
            SourcePart(
                part_key="archive",
                part_kind="single",
                part_label=None,
                path=path,
            ),
        ),
    )


def _multipart_spec(
    data_root: Path,
    *,
    category: str,
    yyyymm: str,
    directory: Path,
    filename: Any,
) -> SourceSpec:
    del data_root
    catalog = category_by_code[category]
    return SourceSpec(
        category=category,
        yyyymm=yyyymm,
        role=catalog.default_role,
        group_kind=catalog.group_kind,
        parts=tuple(
            SourcePart(
                part_key=code,
                part_kind="sido",
                part_label=sido_name,
                path=directory / filename(sido_name),
            )
            for code, sido_name in SIDO_PARTS
        ),
    )


async def apply_schema(engine: AsyncEngine) -> None:
    from sqlalchemy.exc import ProgrammingError

    statements = (*iter_sql_statements(SCHEMA_SQL), *iter_sql_statements(INDEX_SQL))
    async with engine.connect() as conn:
        for statement in statements:
            try:
                async with conn.begin():
                    await conn.execute(text(statement))
            except ProgrammingError as exc:
                code = str(getattr(exc.orig, "sqlstate", ""))
                if code not in {"42710", "42P07", "42P16"} and "already exists" not in str(exc):
                    raise


async def database_name(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        return str(await conn.scalar(text("SELECT current_database()")))


async def assert_no_active_jobs(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT job_id, kind, state, current_stage
  FROM load_jobs
 WHERE state IN ('queued', 'running')
 ORDER BY created_at
 LIMIT 10
"""
                )
            )
        ).mappings().all()
    if rows:
        payload = json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str)
        raise ConflictError(f"queued/running load_jobs가 남아 있습니다: {payload}")


async def current_active_match_set(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        row = await conn.scalar(
            text(
                "SELECT source_match_set_id FROM ops.source_match_sets "
                "WHERE state = 'active' LIMIT 1"
            )
        )
    return str(row) if row else None


async def restore_active_match_set(
    engine: AsyncEngine,
    *,
    prior_active_id: str | None,
    activated_match_set_id: str | None,
) -> None:
    """Restore the prior active match-set *pointer* (scratch-DB slot restore).

    NOTE: this only flips ``ops.source_match_sets.active`` back; it does NOT undo
    the ``mv_refresh strategy='swap'`` that already promoted this run's data into
    the serving MVs, nor retire the new ``serving_release``. So the serving data
    stays displaced even in default (non --promote) mode — run only against a
    scratch DB (see this script's docstring and docs/t213-phase2-live-loading.md).
    """
    if prior_active_id is None or activated_match_set_id is None:
        return
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops.source_match_sets SET state = 'retired', updated_at = now() "
                "WHERE source_match_set_id = :id AND state = 'active'"
            ),
            {"id": activated_match_set_id},
        )
        restored = await conn.execute(
            text(
                "UPDATE ops.source_match_sets SET state = 'active', updated_at = now() "
                "WHERE source_match_set_id = :id AND state = 'retired'"
            ),
            {"id": prior_active_id},
        )
    if restored.rowcount:
        print(f"[match-set] restored prior active match set {prior_active_id}")
    else:
        print(
            f"[match-set] WARNING: prior active match set {prior_active_id} was not "
            "in 'retired' state; restore is a no-op (it may have changed concurrently)"
        )


async def register_sources(
    *,
    engine: AsyncEngine,
    settings: Settings,
    specs: Sequence[SourceSpec],
    output_dir: Path,
    run_id: str,
) -> tuple[RegisteredGroup, ...]:
    rustfs_config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(rustfs_config)
    await rustfs.ensure_bucket()
    upload_repo = SourceUploadSessionRepository(engine)
    registrar = SourceGroupRegistrar(engine)
    validation_cache = output_dir / "materialized" / "validation"
    registered: list[RegisteredGroup] = []
    for spec in specs:
        print(f"[register] {spec.category} {spec.yyyymm} ({len(spec.parts)} file)")
        validation_parts = materialize_for_validation(spec, validation_cache)
        validation = validate_group_manifest(
            scan_group_manifest(
                category=spec.category,
                group_kind=spec.group_kind,
                parts=validation_parts,
            )
        )
        if validation.outcome == "failed":
            raise RuntimeError(f"{spec.category} 구조 검증 실패: {validation.reasons}")
        create = await upload_repo.create_session(
            UploadSessionCreateRequest(
                category=spec.category,
                user_yyyymm=spec.yyyymm,
                display_name=f"[{RUN_MARKER} {run_id}] {spec.category} {spec.yyyymm}",
                storage_kind="rustfs",
                upload_strategy="multipart",
            ),
            bucket=rustfs_config.bucket,
            prefix=rustfs_config.prefix,
            created_by=ACTOR,
        )
        if create.conflict:
            raise ConflictError(
                f"{spec.category}/{spec.yyyymm}에 진행 중인 upload session이 있습니다: "
                f"{create.session.upload_session_id} state={create.session.state}"
            )
        contexts: list[RegisterContext] = []
        for part in spec.parts:
            digest = await sha256_file(part.path)
            size = part.path.stat().st_size
            object_key = rustfs_config.object_key(
                "t213-live",
                run_id,
                spec.category,
                f"{part.part_key}-{part.path.name}",
            )
            print(f"  put rustfs {part.part_key}: {part.path.name} ({size:,} bytes)")
            etag = await rustfs.put_file(object_key, part.path, sha256=digest)
            await upload_repo.record_part(
                create.session.upload_session_id,
                part_key=part.part_key,
                part_number=1,
                part_etag=etag,
                part_sha256=digest,
                received_bytes=size,
                completed=True,
            )
            contexts.append(
                RegisterContext(
                    part_key=part.part_key,
                    part_kind=part.part_kind,
                    part_label=part.part_label,
                    original_filename=part.path.name,
                    sha256=digest,
                    size_bytes=size,
                    object_key=object_key,
                    object_etag=etag,
                    compression_format=_compression_format(part.path),
                )
            )
        response = await registrar.register(
            session_id=create.session.upload_session_id,
            contexts=tuple(contexts),
            structure_validation=validation,
            storage_kind="rustfs",
            bucket=rustfs_config.bucket,
            actor=ACTOR,
            yyyymm_mismatch_ack=False,
            display_name=f"[{RUN_MARKER} {run_id}] {spec.category} {spec.yyyymm}",
        )
        print(
            f"  group={response.source_file_group_id} "
            f"state={response.state}/{response.validation_state} "
            f"sha={str(response.group_sha256 or '')[:16]}"
        )
        registered.append(
            RegisteredGroup(
                spec=spec,
                source_file_group_id=response.source_file_group_id,
                group_sha256=response.group_sha256,
                validation=validation,
            )
        )
    return tuple(registered)


def materialize_for_validation(spec: SourceSpec, cache_root: Path) -> dict[str, Path]:
    if spec.category != "navi_full":
        return {part.part_key: part.path for part in spec.parts}
    target = cache_root / spec.category
    marker = target / ".ktg-materialized-ok"
    if not marker.exists():
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        extract_navi_7z(spec.parts[0].path, target)
        marker.write_text(str(spec.parts[0].path) + "\n", encoding="utf-8")
    return {"archive": target}


def extract_navi_7z(archive: Path, target: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if seven_zip is None:
        raise RuntimeError("7z/7zz/7za command not found; navi .7z를 풀 수 없습니다")
    subprocess.run(
        [
            seven_zip,
            "x",
            "-y",
            f"-o{target}",
            str(archive),
            "match_build_*.txt",
            "match_rs_entrc.txt",
            "match_jibun_*.txt",
        ],
        check=True,
    )


def _compression_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "directory"


async def build_match_set(
    engine: AsyncEngine,
    *,
    registered: Sequence[RegisteredGroup],
    profile: RunProfile,
    run_id: str,
) -> str:
    repo = SourceMatchSetRepository(engine)
    detail = await repo.create_match_set(
        SourceMatchSetCreateRequest(
            name=f"{RUN_MARKER} {run_id} {profile}",
            description="T-213 proper nationwide live source pipeline run",
            profile=profile,
            items=tuple(
                SourceMatchSetItemRequest(
                    category=item.spec.category,
                    role=item.spec.role,
                    source_file_group_id=item.source_file_group_id,
                    required=True,
                    effective_yyyymm=item.spec.yyyymm,
                    load_order=index + 1,
                    metadata={"runbook": RUN_MARKER, "run_id": run_id},
                )
                for index, item in enumerate(registered)
            ),
            metadata={"runbook": RUN_MARKER, "run_id": run_id},
        ),
        actor=ACTOR,
    )
    msid = detail.match_set.source_match_set_id
    validated = await repo.validate_match_set(msid, actor=ACTOR)
    if not validated.ok:
        raise RuntimeError(f"match set validate 실패: {validated.reasons}")
    activated = await repo.activate_match_set(msid, actor=ACTOR)
    print(
        f"[match-set] id={msid} state={activated.state} "
        f"retired={activated.retired_match_set_id}"
    )
    return msid


def relocate_batch_payload(batch_payload: dict[str, Any], staging_root: Path) -> dict[str, Any]:
    relocated = dict(batch_payload)
    relocated["staging_dir"] = str(staging_root)
    children: list[dict[str, Any]] = []
    for child in batch_payload["children"]:
        child_copy = {"kind": child["kind"], "payload": dict(child["payload"])}
        category = _category_from_child_payload(child_copy["payload"])
        child_copy["payload"]["path"] = str(staging_root / category)
        children.append(child_copy)
    relocated["children"] = children
    return relocated


def _category_from_child_payload(payload: dict[str, Any]) -> str:
    source_set = payload.get("source_file_group_id")
    path = str(payload.get("path", ""))
    if path:
        return Path(path).name
    raise RuntimeError(f"child payload에 category path가 없습니다: {source_set}")


def materialize_staging(
    specs: Sequence[SourceSpec],
    *,
    batch_payload: dict[str, Any],
    validation_cache: Path,
) -> None:
    path_by_category = {
        _category_from_child_payload(child["payload"]): Path(child["payload"]["path"])
        for child in batch_payload["children"]
    }
    for spec in specs:
        target = path_by_category[spec.category]
        marker = target / ".ktg-materialized-ok"
        if marker.exists():
            continue
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        print(f"[stage] {spec.category} -> {target}")
        if spec.category in {"roadname_hangul_full", "locsum_full"}:
            extract_zip(spec.parts[0].path, target)
        elif spec.category == "navi_full":
            cached = validation_cache / spec.category
            if not cached.exists():
                extract_navi_7z(spec.parts[0].path, cached)
            for file in cached.glob("*.txt"):
                link_or_copy(file, target / file.name)
        elif spec.category == "electronic_map_full":
            for part in spec.parts:
                assert part.part_label is not None
                extract_zip(part.path, target / part.part_label)
        elif spec.category in {"roadaddr_entrance_full", "zone_shape_full"}:
            for part in spec.parts:
                link_or_copy(part.path, target / part.path.name)
        else:
            raise RuntimeError(f"unsupported staging category: {spec.category}")
        marker.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")


def extract_zip(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(target)


def link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        destination.symlink_to(source)
    except OSError:
        shutil.copy2(source, destination)


async def enqueue_and_wait(
    *,
    engine: AsyncEngine,
    client: AsyncAddressClient,
    source_match_set_id: str,
    batch_payload: dict[str, Any],
    force_promotion: bool,
    force_promotion_reason: str | None,
    poll_interval_seconds: float,
    timeout_minutes: float,
) -> str:
    queue = _jobs.JobQueue(engine)
    _register_default_handlers(queue, engine)
    job_id = await queue.enqueue_batch(batch_payload)
    await client.record_rebuild_enqueued(
        source_match_set_id,
        actor=ACTOR,
        job_id=job_id,
        load_batch_id=job_id,
        forced_promotion=force_promotion,
        reason=force_promotion_reason,
    )
    print(f"[batch] enqueued job_id={job_id}")
    await wait_for_batch(
        engine,
        job_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_minutes=timeout_minutes,
    )
    return job_id


async def wait_for_batch(
    engine: AsyncEngine,
    job_id: str,
    *,
    poll_interval_seconds: float,
    timeout_minutes: float,
) -> None:
    started = time.monotonic()
    last_line = ""
    while True:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
SELECT state, current_stage, progress, error_message
  FROM load_jobs
 WHERE job_id = :job_id
"""
                    ),
                    {"job_id": job_id},
                )
            ).mappings().one()
        line = (
            f"[batch] state={row['state']} stage={row['current_stage']} "
            f"progress={float(row['progress'] or 0):.3f}"
        )
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if row["state"] == "done":
            return
        if row["state"] in {"failed", "cancelled"}:
            raise RuntimeError(f"batch {row['state']}: {row['error_message']}")
        if timeout_minutes > 0 and time.monotonic() - started > timeout_minutes * 60:
            raise TimeoutError(f"batch timeout: {job_id}")
        await asyncio.sleep(poll_interval_seconds)


async def collect_row_counts(engine: AsyncEngine) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    async with engine.connect() as conn:
        for table_name in ROW_COUNT_TABLES:
            exists = await conn.scalar(text("SELECT to_regclass(:name)"), {"name": table_name})
            if exists is None:
                counts[table_name] = None
                continue
            counts[table_name] = int(
                await conn.scalar(text(f"SELECT count(*) FROM {table_name}")) or 0
            )
    return counts


async def collect_job_rows(engine: AsyncEngine, job_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT job_id, kind, state, current_stage, progress, error_message,
       started_at, finished_at
  FROM load_jobs
 WHERE job_id = :job_id OR load_batch_id = :job_id
 ORDER BY created_at
"""
                ),
                {"job_id": job_id},
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def plan_payload(specs: Sequence[SourceSpec], profile: RunProfile) -> dict[str, Any]:
    return {
        "profile": profile,
        "categories": [
            {
                "category": spec.category,
                "yyyymm": spec.yyyymm,
                "role": spec.role,
                "group_kind": spec.group_kind,
                "files": [
                    {
                        "part_key": part.part_key,
                        "part_label": part.part_label,
                        "path": str(part.path),
                        "size_bytes": part.path.stat().st_size if part.path.exists() else None,
                    }
                    for part in spec.parts
                ],
            }
            for spec in specs
        ],
    }


async def run(args: argparse.Namespace) -> int:
    run_started = datetime.now(UTC)
    run_id = run_started.strftime("%Y%m%dT%H%M%SZ")
    output_dir = (args.output_dir or Path("artifacts") / f"t213-live-{run_id}").resolve()
    profile: RunProfile = args.profile
    specs = build_source_specs(args.data_root, profile)
    print(json.dumps(plan_payload(specs, profile), ensure_ascii=False, indent=2))
    if not args.execute:
        print("PLAN ONLY: --execute를 붙이면 실제 T-213 proper load를 실행합니다.")
        return 0

    settings = Settings(pg_dsn=args.dsn)
    engine = make_async_engine(settings)
    client = AsyncAddressClient(settings=settings, engine=engine)
    prior_active_id: str | None = None
    activated_match_set_id: str | None = None
    active_restored = False
    try:
        db_name = await database_name(engine)
        if not args.allow_destructive:
            raise SystemExit(
                "T-213 live runbook은 active match set과 serving DB를 바꾸므로 "
                "--allow-destructive가 필요합니다"
            )
        expected_confirmation = f"RUN-T213-LIVE {db_name}"
        if args.typed_confirmation != expected_confirmation:
            raise SystemExit(
                "typed confirmation이 필요합니다: "
                f"--typed-confirmation \"{expected_confirmation}\""
            )
        if args.force_promotion and not args.force_promotion_reason:
            raise SystemExit("--force-promotion 사용 시 --force-promotion-reason이 필요합니다")
        await apply_schema(engine)
        await client.seed_consistency_registry()
        if not args.allow_existing_jobs:
            await assert_no_active_jobs(engine)
        prior_active_id = await current_active_match_set(engine)
        if prior_active_id is not None:
            print(
                "[match-set] prior active match set "
                f"{prior_active_id} will be restored unless --promote-active-match-set is set"
            )

        registered = await register_sources(
            engine=engine,
            settings=settings,
            specs=specs,
            output_dir=output_dir,
            run_id=run_id,
        )
        msid = await build_match_set(
            engine,
            registered=registered,
            profile=profile,
            run_id=run_id,
        )
        activated_match_set_id = msid
        response, batch_payload = await client.prepare_source_match_set_rebuild(
            msid,
            actor=ACTOR,
            force_promotion=bool(args.force_promotion),
            typed_confirmation=f"REBUILD-PROMOTE {msid}" if args.force_promotion else None,
            reason=args.force_promotion_reason,
        )
        if batch_payload is None:
            raise RuntimeError(f"integrity gate 실패: {response}")
        staging_root = output_dir / "rebuild_staging" / msid
        relocated = relocate_batch_payload(batch_payload, staging_root)
        materialize_staging(
            specs,
            batch_payload=relocated,
            validation_cache=output_dir / "materialized" / "validation",
        )
        job_id = await enqueue_and_wait(
            engine=engine,
            client=client,
            source_match_set_id=msid,
            batch_payload=relocated,
            force_promotion=bool(args.force_promotion),
            force_promotion_reason=args.force_promotion_reason,
            poll_interval_seconds=float(args.poll_interval_seconds),
            timeout_minutes=float(args.timeout_minutes),
        )
        row_counts = await collect_row_counts(engine)
        job_rows = await collect_job_rows(engine, job_id)
        summary = {
            "schema_version": 1,
            "run_id": run_id,
            "runbook": RUN_MARKER,
            "profile": profile,
            "started_at": run_started.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "database": db_name,
            "source_match_set_id": msid,
            "load_batch_id": job_id,
            "force_promotion": bool(args.force_promotion),
            "promote_active_match_set": bool(args.promote_active_match_set),
            "output_dir": str(output_dir),
            "registered_groups": [
                {
                    "category": item.spec.category,
                    "yyyymm": item.spec.yyyymm,
                    "source_file_group_id": item.source_file_group_id,
                    "group_sha256": item.group_sha256,
                    "validation_outcome": item.validation.outcome,
                    "validation_reasons": item.validation.reasons,
                }
                for item in registered
            ],
            "row_counts": row_counts,
            "jobs": job_rows,
        }
        write_summary(output_dir / "t213-live-summary.json", summary)
        print(
            json.dumps(
                {"row_counts": row_counts, "summary": str(output_dir)},
                ensure_ascii=False,
            )
        )
        if not args.promote_active_match_set:
            await restore_active_match_set(
                engine,
                prior_active_id=prior_active_id,
                activated_match_set_id=activated_match_set_id,
            )
            active_restored = True
        return 0
    finally:
        if (
            activated_match_set_id is not None
            and prior_active_id is not None
            and not args.promote_active_match_set
            and not active_restored
        ):
            try:
                await restore_active_match_set(
                    engine,
                    prior_active_id=prior_active_id,
                    activated_match_set_id=activated_match_set_id,
                )
            except Exception as exc:
                print(f"[match-set] WARNING: prior active restore failed: {exc}")
        await engine.dispose()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.execute and not args.dsn:
        parser.error("no DSN: pass --dsn or set KTG_TEST_PG_DSN/KTG_PG_DSN")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
