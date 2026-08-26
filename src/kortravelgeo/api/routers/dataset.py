"""External dataset-version API — change detection + history (T-291c, ADR-067).

``POST /v2/dataset/version`` and ``POST /v2/dataset/history``. Same public-key auth as every
other v2 endpoint (ADR-064, no new scope) and the same v2 structured-400 envelope
(``routers.v2._V2_VALIDATION_RESPONSES``). Responses always carry ``Cache-Control: no-store``
(design doc §1) — this is a change-detection surface; a stale cached response defeats the
whole point.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.api.routers.v2 import _V2_VALIDATION_RESPONSES
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.dataset_version import decode_history_cursor, encode_history_cursor
from kortravelgeo.dto.v2 import (
    DatasetHistoryInput,
    DatasetHistoryResponse,
    DatasetVersionInput,
    DatasetVersionResponse,
)
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.admin_repo import AdminRepository

router = APIRouter(tags=["v2-dataset"])


@router.post(
    "/version",
    response_model=DatasetVersionResponse,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def dataset_version(
    req: DatasetVersionInput,
    response: Response,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
) -> DatasetVersionResponse:
    response.headers["Cache-Control"] = "no-store"
    repo = AdminRepository(client._engine())
    current = await repo.current_dataset_version()
    if current is None:
        # No active release — not an error (design doc §1.1): a fresh/emptied DB is a real
        # state, and a consumer's error-handling branch shouldn't fire for it.
        return DatasetVersionResponse(status="OK", input=req, available=False)
    if req.known_version is None:
        return DatasetVersionResponse(status="OK", input=req, available=True, current=current)
    if req.known_version == current.version_token:
        return DatasetVersionResponse(
            status="OK",
            input=req,
            available=True,
            current=current,
            changed=False,
            known_version_found=True,
        )
    found = await repo.find_dataset_version(req.known_version) is not None
    return DatasetVersionResponse(
        status="OK",
        input=req,
        available=True,
        current=current,
        changed=True,
        known_version_found=found,
    )


@router.post(
    "/history",
    response_model=DatasetHistoryResponse,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def dataset_history(
    req: DatasetHistoryInput,
    response: Response,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
) -> DatasetHistoryResponse:
    response.headers["Cache-Control"] = "no-store"
    repo = AdminRepository(client._engine())

    before: tuple[datetime, str] | None = None
    if req.cursor is not None:
        decoded = decode_history_cursor(req.cursor)
        if decoded is None:
            msg = "cursor를 해석할 수 없습니다"
            raise InvalidInputError(msg, hint="이력 처음부터 재조회(cursor 생략)")
        before = decoded

    since: tuple[datetime, str] | None = None
    since_found: bool | None = None
    if req.since_version is not None:
        since_entry = await repo.find_dataset_version(req.since_version)
        since_found = since_entry is not None
        if since_entry is not None:
            since = (since_entry.activated_at, since_entry.version_token)
        # not found: since stays None (no lower bound) — "최신 페이지를 반환하고 전체
        # 재동기화 규약" (design doc §1.2), i.e. fall through to an unbounded-below page.

    page, has_more = await repo.dataset_version_history(limit=req.limit, before=before, since=since)
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_history_cursor(last.activated_at, last.version_token)

    return DatasetHistoryResponse(
        status="OK",
        input=req,
        since_found=since_found,
        entries=tuple(page),
        next_cursor=next_cursor,
    )
