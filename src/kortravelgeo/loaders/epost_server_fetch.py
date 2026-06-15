"""Manual epost server-fetch source registration flow (T-207)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.source_validation import GroupValidation, PartValidation
from kortravelgeo.dto.source import (
    EpostLoadJobKind,
    EpostServerFetchRequest,
    RegisterResponse,
    UploadSessionCreateRequest,
    UploadSessionStatus,
)
from kortravelgeo.exceptions import ConflictError, InvalidInputError, LoaderError
from kortravelgeo.infra.rustfs import RustfsClient, require_enabled_rustfs, sha256_file
from kortravelgeo.infra.source_group_service import RegisterContext, SourceGroupRegistrar
from kortravelgeo.infra.source_upload_repo import SourceUploadSessionRepository
from kortravelgeo.loaders.epost_downloader import (
    discover_epost_files,
    download_epost_zip,
    extract_epost_zip,
)
from kortravelgeo.loaders.epost_validation import (
    PostalValidationSummary,
    ensure_postal_validation_passed,
    validate_bulk_file,
    validate_pobox_file,
)
from kortravelgeo.settings import Settings

PostalFetchKind = Literal["pobox", "bulk"]

_CATEGORY_TO_POSTAL_KIND: dict[str, PostalFetchKind] = {
    "epost_pobox_full": "pobox",
    "epost_bulk_full": "bulk",
}
_CATEGORY_TO_LOAD_KIND: dict[str, EpostLoadJobKind] = {
    "epost_pobox_full": "pobox_load",
    "epost_bulk_full": "bulk_load",
}


@dataclass(frozen=True, slots=True)
class EpostServerFetchResult:
    """Internal result passed from the fetch service to the admin router."""

    category: str
    upload_session: UploadSessionStatus
    register: RegisterResponse
    selected_path: Path
    selected_filename: str
    validation: PostalValidationSummary
    warnings: tuple[str, ...]
    load_job_kind: EpostLoadJobKind
    load_payload: dict[str, Any]


async def fetch_epost_source_file(
    *,
    engine: AsyncEngine,
    settings: Settings,
    req: EpostServerFetchRequest,
    actor: str | None,
) -> EpostServerFetchResult:
    """Download, validate, RustFS-register, and prepare a postal load job.

    This is the explicit manual server-fetch exception in T-207. It never
    creates or edits a source match set and never triggers a core rebuild.
    """

    postal_kind = _postal_kind(req.category)
    load_kind = _CATEGORY_TO_LOAD_KIND[req.category]
    rustfs_config = require_enabled_rustfs(settings)
    upload_repo = SourceUploadSessionRepository(engine)
    display_name = (
        req.display_name
        or f"epost {postal_kind} server-fetch {req.user_yyyymm}"
    )
    created = await upload_repo.create_session(
        UploadSessionCreateRequest(
            category=req.category,
            user_yyyymm=req.user_yyyymm,
            display_name=display_name,
            storage_kind="rustfs",
            upload_strategy="multipart",
        ),
        bucket=rustfs_config.bucket,
        prefix=rustfs_config.prefix,
        created_by=actor,
    )
    if created.conflict:
        existing = created.session
        raise ConflictError(
            f"{existing.category}/{existing.user_yyyymm}에 진행 중인 epost fetch 세션이 있습니다",
            hint=existing.upload_session_id,
        )

    session = created.session
    run_dir = _fetch_run_dir(settings.loader_data_dir, session.upload_session_id)
    failure_state = "failed_upload"
    try:
        await upload_repo.update_state(session.upload_session_id, state="uploading")
        zip_path = await download_epost_zip(
            settings,
            run_dir / "download",
            download_kind=req.download_kind or _default_download_kind(postal_kind),
        )
        failure_state = "failed_extract"
        await upload_repo.update_state(session.upload_session_id, state="extracting")
        extracted_dir = extract_epost_zip(zip_path, run_dir / "extract")
        failure_state = "failed_structure"
        selected = _select_epost_file(extracted_dir, postal_kind)

        await upload_repo.update_state(
            session.upload_session_id,
            state="validating_structure",
        )
        validation = _validate_selected_file(selected, postal_kind)
        ensure_postal_validation_passed(validation)
        warnings = await _warnings_for_request(
            engine,
            user_yyyymm=req.user_yyyymm,
            validation=validation,
        )

        failure_state = "failed_rustfs_put"
        await upload_repo.update_state(session.upload_session_id, state="storing_to_rustfs")
        digest = await sha256_file(selected)
        size = selected.stat().st_size
        object_key = rustfs_config.object_key(
            "source-files",
            req.category,
            req.user_yyyymm,
            session.source_file_group_id,
            session.upload_session_id,
            "archive",
            selected.name,
        )
        rustfs = RustfsClient(rustfs_config)
        await rustfs.ensure_bucket()
        try:
            object_etag = await rustfs.put_file(object_key, selected, sha256=digest)
        except Exception as exc:
            await _fail_session(
                upload_repo,
                session.upload_session_id,
                state="failed_rustfs_put",
                error=exc,
            )
            raise
        await upload_repo.record_part(
            session.upload_session_id,
            part_key="archive",
            part_number=1,
            part_etag=object_etag,
            part_sha256=digest,
            received_bytes=size,
            completed=True,
        )

        failure_state = "failed_register"
        await upload_repo.update_state(
            session.upload_session_id,
            state="awaiting_registration",
        )
        structure_validation = _structure_validation(
            category=req.category,
            validation=validation,
            warnings=warnings,
        )
        try:
            register = await SourceGroupRegistrar(engine).register(
                session_id=session.upload_session_id,
                contexts=(
                    RegisterContext(
                        part_key="archive",
                        part_kind="single",
                        part_label=None,
                        original_filename=selected.name,
                        sha256=digest,
                        size_bytes=size,
                        object_key=object_key,
                        object_etag=object_etag,
                        compression_format="txt",
                    ),
                ),
                structure_validation=structure_validation,
                storage_kind="rustfs",
                bucket=rustfs_config.bucket,
                actor=actor,
                yyyymm_mismatch_ack=req.yyyymm_mismatch_ack,
                display_name=display_name,
            )
        except Exception as exc:
            await _fail_session(
                upload_repo,
                session.upload_session_id,
                state="failed_register",
                error=exc,
            )
            raise
        updated_session = await upload_repo.get_session(session.upload_session_id)
        if updated_session is None:
            raise InvalidInputError(
                f"upload session disappeared: {session.upload_session_id}"
            )
        return EpostServerFetchResult(
            category=req.category,
            upload_session=updated_session,
            register=register,
            selected_path=selected,
            selected_filename=selected.name,
            validation=validation,
            warnings=warnings,
            load_job_kind=load_kind,
            load_payload={
                "path": str(selected),
                "source_yyyymm": req.user_yyyymm,
                "source_file_group_id": register.source_file_group_id,
                "category": req.category,
                "validation": _validation_payload(validation),
                "warnings": list(warnings),
            },
        )
    except LoaderError as exc:
        await _fail_session(
            upload_repo,
            session.upload_session_id,
            state=failure_state,
            error=exc,
        )
        raise
    except Exception as exc:
        current = await upload_repo.get_session(session.upload_session_id)
        if current is not None and not current.state.startswith("failed_"):
            await _fail_session(
                upload_repo,
                session.upload_session_id,
                state=failure_state,
                error=exc,
            )
        raise


def _postal_kind(category: str) -> PostalFetchKind:
    try:
        return _CATEGORY_TO_POSTAL_KIND[category]
    except KeyError as exc:
        raise InvalidInputError(f"unsupported epost server-fetch category: {category}") from exc


def _default_download_kind(postal_kind: PostalFetchKind) -> str:
    return "4" if postal_kind == "pobox" else "1"


def _fetch_run_dir(loader_data_dir: Path, upload_session_id: str) -> Path:
    return loader_data_dir / "epost" / "server-fetch" / upload_session_id


def _select_epost_file(extracted_dir: Path, postal_kind: PostalFetchKind) -> Path:
    pobox_file, bulk_file = discover_epost_files(extracted_dir)
    selected = pobox_file if postal_kind == "pobox" else bulk_file
    if selected is None:
        label = "사서함" if postal_kind == "pobox" else "다량배달처"
        raise LoaderError(f"epost ZIP에서 {label} 파일을 찾지 못했습니다")
    return selected


def _validate_selected_file(
    selected: Path,
    postal_kind: PostalFetchKind,
) -> PostalValidationSummary:
    return validate_pobox_file(selected) if postal_kind == "pobox" else validate_bulk_file(selected)


async def _warnings_for_request(
    engine: AsyncEngine,
    *,
    user_yyyymm: str,
    validation: PostalValidationSummary,
) -> tuple[str, ...]:
    warnings: list[str] = []
    current_yyyymm = await _current_juso_source_yyyymm(engine)
    if current_yyyymm and current_yyyymm != user_yyyymm:
        warnings.append(
            "epost 기준월이 현재 도로명주소 serving 기준월과 다릅니다: "
            f"epost={user_yyyymm}, serving={current_yyyymm}"
        )
    if validation.encoding and validation.encoding != "utf-8-sig":
        warnings.append(f"epost 텍스트 인코딩: {validation.encoding}")
    return tuple(warnings)


async def _current_juso_source_yyyymm(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('tl_juso_text')"))
        if exists is None:
            return None
        value = await conn.scalar(
            text(
                """
SELECT source_yyyymm
  FROM tl_juso_text
 WHERE source_yyyymm IS NOT NULL
 GROUP BY source_yyyymm
 ORDER BY count(*) DESC, source_yyyymm DESC
 LIMIT 1
"""
            )
        )
    return str(value) if value else None


def _structure_validation(
    *,
    category: str,
    validation: PostalValidationSummary,
    warnings: tuple[str, ...],
) -> GroupValidation:
    outcome: Literal["passed", "warning"] = "warning" if warnings else "passed"
    part = PartValidation(
        part_key="archive",
        outcome=outcome,
        warnings=(
            f"rows={validation.row_count}",
            f"encoding={validation.encoding or 'unknown'}",
            *warnings,
        ),
    )
    return GroupValidation(
        category=category,
        outcome=outcome,
        parts=(part,),
        coverage={"archive": "present"},
    )


def _validation_payload(validation: PostalValidationSummary) -> dict[str, Any]:
    return asdict(validation)


async def _fail_session(
    repo: SourceUploadSessionRepository,
    session_id: str,
    *,
    state: str,
    error: BaseException,
) -> None:
    await repo.update_state(session_id, state=state, error_message=str(error))
