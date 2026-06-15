#!/usr/bin/env python3
"""T-126 acceptance follow-up runner.

T-215 left two acceptance gaps:

* REST c64 tail needed environment-separated reruns.
* C11~C17 run-validation had no optional validation sources in the active
  T-213 r3 match set, so every optional case was skipped.

This runner closes the second gap without rebuilding or promoting serving data.
It registers the optional validation archives into RustFS/source registry,
creates a ``custom`` source match set that combines the current baseline source
groups with those optional groups, and runs
``AsyncAddressClient.run_consistency_validation()`` against that match set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.source_categories import SIDO_PARTS, category_by_code
from kortravelgeo.core.source_validation import validate_group_manifest
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
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.core.source_validation import GroupValidation
    from kortravelgeo.dto.source import (
        SourceFileCategory,
        SourceFilePartKind,
        SourceGroupKind,
        SourceMatchSetItemRole,
    )


RUN_MARKER = "t126-acceptance-followup"
ACTOR = RUN_MARKER


@dataclass(frozen=True, slots=True)
class SourcePart:
    part_key: str
    part_kind: SourceFilePartKind
    part_label: str | None
    path: Path


@dataclass(frozen=True, slots=True)
class SourceSpec:
    category: SourceFileCategory
    yyyymm: str
    role: SourceMatchSetItemRole
    group_kind: SourceGroupKind
    parts: tuple[SourcePart, ...]


@dataclass(frozen=True, slots=True)
class RegisteredGroup:
    spec: SourceSpec
    source_file_group_id: str
    group_sha256: str | None
    validation: GroupValidation | None
    reused: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.getenv("KTG_JUSO_DATA_ROOT", _default_data_root())),
        help="도로명주소 원천 root. 기본값은 KTG_JUSO_DATA_ROOT 또는 /mnt/f/dev/geodata/juso.",
    )
    parser.add_argument(
        "--dsn",
        default=os.getenv("KTG_TEST_PG_DSN") or os.getenv("KTG_PG_DSN"),
        help="대상 PostgreSQL DSN. execute 모드에서는 필수.",
    )
    parser.add_argument(
        "--base-match-set-id",
        help="기준 match set. 생략하면 현재 active source match set을 사용한다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="artifact 출력 디렉터리. 기본값은 artifacts/t126-followup-<run-id>.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 RustFS 등록, custom match set 생성, run-validation을 수행한다.",
    )
    parser.add_argument(
        "--no-reuse-existing",
        action="store_true",
        help="같은 category/user_yyyymm의 available group이 있어도 새로 등록한다.",
    )
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        choices=[f"C{n}" for n in range(11, 18)],
        help="실행할 C11~C17 case. 여러 번 지정 가능하며 생략하면 전체.",
    )
    return parser


def _default_data_root() -> str:
    candidates = (
        Path("/mnt/f/dev/geodata/juso"),
        Path("data/juso"),
        Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def build_optional_source_specs(data_root: Path) -> tuple[SourceSpec, ...]:
    root = data_root.expanduser().resolve()
    unused = root / "unused"
    specs = (
        _multipart_spec(
            category="roadaddr_building_shape_bundle",
            yyyymm="202604",
            directory=_source_dir(unused / "도로명주소 건물 도형", "202604"),
            filename=lambda sido_name: f"건물도형_전체분_{sido_name}.zip",
        ),
        _multipart_spec(
            category="detail_dong_shape_bundle",
            yyyymm="202604",
            directory=_source_dir(unused / "건물군 내 상세주소 동 도형", "202604"),
            filename=lambda sido_name: f"건물군내동도형_전체분_{sido_name}.zip",
        ),
        _single_spec(
            category="detail_address_db_full",
            yyyymm="202604",
            path=unused / "202604_상세주소DB_전체분.zip",
        ),
        _single_spec(
            category="national_point_grid_shape",
            yyyymm="202405",
            path=unused / "국가지점번호도형_5월분.zip",
        ),
        _single_spec(
            category="national_point_grid_center",
            yyyymm="202405",
            path=unused / "국가지점번호중심점_5월분.zip",
        ),
        _single_spec(
            category="civil_service_institution_map",
            yyyymm="202401",
            path=unused / "민원행정기관전자지도_240124.zip",
        ),
        _single_spec(
            category="address_db_full",
            yyyymm="202605",
            path=unused / "202605_주소DB_전체분.zip",
        ),
        _single_spec(
            category="building_db_full",
            yyyymm="202605",
            path=unused / "202605_건물DB_전체분.zip",
        ),
    )
    missing = [str(part.path) for spec in specs for part in spec.parts if not part.path.exists()]
    if missing:
        joined = "\n  - ".join(missing)
        raise SystemExit(f"필수 optional 원천 파일이 없습니다:\n  - {joined}")
    return specs


def _source_dir(parent: Path, yyyymm: str) -> Path:
    dated = parent / yyyymm
    return dated if dated.exists() else parent


def _single_spec(*, category: str, yyyymm: str, path: Path) -> SourceSpec:
    catalog = category_by_code[category]
    return SourceSpec(
        category=cast("SourceFileCategory", category),
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
    *,
    category: str,
    yyyymm: str,
    directory: Path,
    filename: Callable[[str], str],
) -> SourceSpec:
    catalog = category_by_code[category]
    return SourceSpec(
        category=cast("SourceFileCategory", category),
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


def plan_payload(specs: Sequence[SourceSpec]) -> dict[str, Any]:
    return {
        "runbook": RUN_MARKER,
        "optional_categories": [
            {
                "category": spec.category,
                "yyyymm": spec.yyyymm,
                "role": spec.role,
                "group_kind": spec.group_kind,
                "file_count": len(spec.parts),
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


async def database_name(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        return str(await conn.scalar(text("SELECT current_database()")))


async def active_match_set_id(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                """
SELECT source_match_set_id
  FROM ops.source_match_sets
 WHERE state = 'active'
 ORDER BY updated_at DESC
 LIMIT 1
"""
            )
        )
    if value is None:
        raise RuntimeError("active source match set이 없습니다")
    return str(value)


async def latest_available_group(
    engine: AsyncEngine, *, category: str, user_yyyymm: str
) -> tuple[str, str | None] | None:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT source_file_group_id, group_sha256
  FROM ops.source_file_groups
 WHERE category = :category
   AND user_yyyymm = :user_yyyymm
   AND state = 'available'
 ORDER BY updated_at DESC
 LIMIT 1
"""
                ),
                {"category": category, "user_yyyymm": user_yyyymm},
            )
        ).mappings().first()
    if row is None:
        return None
    group_sha256 = row["group_sha256"]
    return (
        str(row["source_file_group_id"]),
        str(group_sha256) if group_sha256 is not None else None,
    )


async def register_optional_sources(
    *,
    engine: AsyncEngine,
    settings: Settings,
    specs: Sequence[SourceSpec],
    output_dir: Path,
    run_id: str,
    reuse_existing: bool,
) -> tuple[RegisteredGroup, ...]:
    rustfs_config = require_enabled_rustfs(settings)
    rustfs = RustfsClient(rustfs_config)
    await rustfs.ensure_bucket()
    upload_repo = SourceUploadSessionRepository(engine)
    registrar = SourceGroupRegistrar(engine)
    registered: list[RegisteredGroup] = []
    for spec in specs:
        if reuse_existing:
            existing = await latest_available_group(
                engine, category=spec.category, user_yyyymm=spec.yyyymm
            )
            if existing is not None:
                group_id, group_sha = existing
                print(f"[reuse] {spec.category} {spec.yyyymm} group={group_id}")
                registered.append(
                    RegisteredGroup(
                        spec=spec,
                        source_file_group_id=group_id,
                        group_sha256=group_sha,
                        validation=None,
                        reused=True,
                    )
                )
                continue

        print(f"[register] {spec.category} {spec.yyyymm} ({len(spec.parts)} file)")
        validation = validate_group_manifest(
            scan_group_manifest(
                category=spec.category,
                group_kind=spec.group_kind,
                parts={part.part_key: part.path for part in spec.parts},
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
                "t126-followup",
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
        registered.append(
            RegisteredGroup(
                spec=spec,
                source_file_group_id=response.source_file_group_id,
                group_sha256=response.group_sha256,
                validation=validation,
                reused=False,
            )
        )
    (output_dir / "registered-optional-groups.json").write_text(
        json.dumps(
            [
                {
                    "category": item.spec.category,
                    "yyyymm": item.spec.yyyymm,
                    "source_file_group_id": item.source_file_group_id,
                    "group_sha256": item.group_sha256,
                    "validation_outcome": item.validation.outcome
                    if item.validation is not None
                    else None,
                    "validation_reasons": item.validation.reasons
                    if item.validation is not None
                    else (),
                    "reused": item.reused,
                }
                for item in registered
            ],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return tuple(registered)


def _compression_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "directory"


async def build_custom_match_set(
    engine: AsyncEngine,
    *,
    base_match_set_id: str,
    registered: Sequence[RegisteredGroup],
    run_id: str,
) -> str:
    repo = SourceMatchSetRepository(engine)
    base = await repo.get_match_set(base_match_set_id)
    optional_categories = {item.spec.category for item in registered}
    base_items = [
        SourceMatchSetItemRequest(
            category=item.category,
            role=item.role,
            source_file_group_id=item.source_file_group_id,
            required=item.required,
            omitted=item.omitted,
            omitted_reason=item.omitted_reason,
            effective_yyyymm=item.effective_yyyymm,
            validation_enabled=item.validation_enabled,
            load_order=item.load_order,
            metadata={**item.metadata, "t126_base_match_set_id": base_match_set_id},
        )
        for item in base.items
        if not item.omitted and item.category not in optional_categories
    ]
    offset = max((item.load_order or 0 for item in base.items), default=0)
    optional_items = [
        SourceMatchSetItemRequest(
            category=item.spec.category,
            role=item.spec.role,
            source_file_group_id=item.source_file_group_id,
            required=False,
            omitted=False,
            effective_yyyymm=item.spec.yyyymm,
            validation_enabled=True,
            load_order=offset + index + 1,
            metadata={"runbook": RUN_MARKER, "run_id": run_id, "reused": item.reused},
        )
        for index, item in enumerate(registered)
    ]
    detail = await repo.create_match_set(
        SourceMatchSetCreateRequest(
            name=f"{RUN_MARKER} {run_id}",
            description=(
                "T-126 optional-source run-validation match set. "
                f"Base match set: {base_match_set_id}"
            ),
            profile="custom",
            items=tuple(base_items + optional_items),
            metadata={
                "runbook": RUN_MARKER,
                "run_id": run_id,
                "base_match_set_id": base_match_set_id,
            },
        ),
        actor=ACTOR,
    )
    msid = detail.match_set.source_match_set_id
    validated = await repo.validate_match_set(msid, actor=ACTOR)
    if not validated.ok:
        raise RuntimeError(f"custom match set validate 실패: {validated.reasons}")
    return msid


async def run(args: argparse.Namespace) -> int:
    run_started = datetime.now(UTC)
    run_id = run_started.strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        args.output_dir or Path("artifacts") / f"t126-followup-{run_id}"
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = build_optional_source_specs(args.data_root)
    source_plan = plan_payload(specs)
    (output_dir / "source-plan.json").write_text(
        json.dumps(source_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(source_plan, ensure_ascii=False, indent=2))
    if not args.execute:
        print("PLAN ONLY: --execute를 붙이면 source registry 등록과 run-validation을 실행합니다.")
        return 0
    if not args.dsn:
        raise SystemExit("execute 모드에는 --dsn 또는 KTG_TEST_PG_DSN/KTG_PG_DSN이 필요합니다")

    settings = Settings(pg_dsn=args.dsn)
    engine = make_async_engine(settings)
    client = AsyncAddressClient(settings=settings, engine=engine)
    try:
        db_name = await database_name(engine)
        await client.seed_consistency_registry()
        base_match_set_id = args.base_match_set_id or await active_match_set_id(engine)
        registered = await register_optional_sources(
            engine=engine,
            settings=settings,
            specs=specs,
            output_dir=output_dir,
            run_id=run_id,
            reuse_existing=not args.no_reuse_existing,
        )
        custom_match_set_id = await build_custom_match_set(
            engine,
            base_match_set_id=base_match_set_id,
            registered=registered,
            run_id=run_id,
        )
        validation = await client.run_consistency_validation(
            custom_match_set_id,
            actor=ACTOR,
            cases=tuple(args.cases) if args.cases else None,
        )
        validation_path = output_dir / "c11-c17-run-validation.json"
        validation_path.write_text(
            json.dumps(validation.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        summary = {
            "schema_version": 1,
            "run_id": run_id,
            "runbook": RUN_MARKER,
            "started_at": run_started.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "database": db_name,
            "base_source_match_set_id": base_match_set_id,
            "custom_source_match_set_id": custom_match_set_id,
            "runnable_count": validation.runnable_count,
            "skipped_count": validation.skipped_count,
            "failed_count": validation.failed_count,
            "quarantined_group_ids": validation.quarantined_group_ids,
            "affected_match_set_ids": validation.affected_match_set_ids,
            "output_dir": str(output_dir),
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
