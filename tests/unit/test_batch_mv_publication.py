"""실제 저장소 호출 계약으로 좌표 판정 ID와 릴리스 게시 경계를 검증한다."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.loaders import batch_dag


@pytest.mark.asyncio
@pytest.mark.parametrize("quality_run_id", [None, "quality-1"])
async def test_mv_quality_id_only_reaches_refresh_and_owner_guard_reaches_release(
    monkeypatch: pytest.MonkeyPatch, quality_run_id: str | None
) -> None:
    engine = object()
    repo = create_autospec(AdminRepository, instance=True)
    repo.record_mv_refresh_release.return_value = (
        SimpleNamespace(dataset_snapshot_id="snapshot-1"),
        SimpleNamespace(serving_release_id="release-1"),
    )
    refresh = AsyncMock()
    links = AsyncMock()
    owner_guard = AsyncMock()
    monkeypatch.setattr(batch_dag, "AdminRepository", lambda _: repo)
    monkeypatch.setattr(batch_dag, "refresh_mv", refresh)
    monkeypatch.setattr(batch_dag, "resolve_text_geometry_links", links)
    payload = {"strategy": "swap", "load_batch_id": "batch-1"}
    if quality_run_id is not None:
        payload["serving_quality_run_id"] = quality_run_id

    await batch_dag.run_mv_refresh(
        engine,
        payload=payload,
        job_id="mv-1",
        progress=AsyncMock(),
        publication_guard=owner_guard,
    )

    links.assert_awaited_once_with(engine)
    repo.ensure_load_batch_release_gate.assert_awaited_once_with("batch-1")
    refresh_kwargs = {
        "concurrently": False,
        "strategy": "swap",
        "publication_guard": owner_guard,
    }
    if quality_run_id is not None:
        refresh_kwargs["serving_quality_run_id"] = quality_run_id
    refresh.assert_awaited_once_with(engine, **refresh_kwargs)
    repo.record_mv_refresh_release.assert_awaited_once_with(
        job_id="mv-1",
        load_batch_id="batch-1",
        strategy="swap",
        source_match_set_id=None,
        forced_promotion=False,
        forced_promotion_metadata=None,
        release_kind=None,
        publication_guard=owner_guard,
    )
