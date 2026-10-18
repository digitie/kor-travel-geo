"""실제 PostGIS에서 활성화와 캐시 삭제의 동일 transaction 경계를 확인한다."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from kortravelgeo.infra.cache import GeoCacheRepository
from tests.integration.test_t325_data_fingerprint import (
    _activate,
    _cache_rows,
    _current,
    _seed_cache_row,
)
from tests.integration.test_t325_data_fingerprint import engine as engine

pytestmark = pytest.mark.asyncio


async def _release_count(engine):
    async with engine.connect() as conn:
        return await conn.scalar(text("SELECT count(*) FROM ops.serving_releases"))


async def test_activation_cache_delete_is_not_visible_before_commit(engine, monkeypatch):
    """활성화 transaction 안에서 삭제해도 다른 연결에는 기존 캐시/릴리스가 보인다."""
    await _activate(engine)
    await _seed_cache_row(engine)
    before = await _current(engine)
    count_before = await _release_count(engine)
    cleared = asyncio.Event()
    commit_allowed = asyncio.Event()
    original = GeoCacheRepository.clear_on

    async def hold_after_clear(conn):
        result = await original(conn)
        cleared.set()
        await asyncio.wait_for(commit_allowed.wait(), timeout=10)
        return result

    monkeypatch.setattr(GeoCacheRepository, "clear_on", staticmethod(hold_after_clear))
    task = asyncio.create_task(_activate(engine))
    try:
        await asyncio.wait_for(cleared.wait(), timeout=10)
        assert await _cache_rows(engine) == 1
        assert await _current(engine) == before
        assert await _release_count(engine) == count_before
    finally:
        commit_allowed.set()
        await task
    assert await _cache_rows(engine) == 0
    assert await _release_count(engine) == count_before + 1
    assert (await _current(engine))[0] != before[0]


async def test_failure_after_cache_delete_rolls_back_release_and_cache(engine, monkeypatch):
    """실제 DELETE 뒤 예외가 나면 새 릴리스와 캐시 삭제가 모두 rollback된다."""
    await _activate(engine)
    await _seed_cache_row(engine)
    before = await _current(engine)
    count_before = await _release_count(engine)
    original = GeoCacheRepository.clear_on
    deleted_rows = []

    async def fail_after_clear(conn):
        deleted_rows.append(await original(conn))
        raise RuntimeError("t325 injected failure after real cache delete")

    monkeypatch.setattr(GeoCacheRepository, "clear_on", staticmethod(fail_after_clear))
    with pytest.raises(RuntimeError, match="t325 injected failure"):
        await _activate(engine)
    assert deleted_rows == [1]
    assert await _cache_rows(engine) == 1
    assert await _current(engine) == before
    assert await _release_count(engine) == count_before
