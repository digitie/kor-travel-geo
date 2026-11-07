from __future__ import annotations

import asyncio

import pytest

from kortravelgeo.infra.result_cache import MemoryResultCache


@pytest.mark.asyncio
async def test_hit_returns_independent_mutable_payloads() -> None:
    cache = MemoryResultCache(4096)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        return {"status": "OK", "result": {"values": [1]}}

    first, hit = await cache.get_or_load("key", load, service="search")
    assert not hit
    first["result"]["values"].append(2)
    second, hit = await cache.get_or_load("key", load, service="search")
    assert hit and calls == 1
    assert second["result"]["values"] == [1]
    await cache.aclose()
    assert cache.size_bytes == 0


@pytest.mark.asyncio
async def test_byte_budget_lru_and_oversized_entry_do_not_flush_useful_entries() -> None:
    cache = MemoryResultCache(900)

    async def load():
        return {"status": "OK", "value": "small"}

    async def large():
        return {"status": "OK", "value": "x" * 5000}

    await cache.get_or_load("a", load, service="search")
    await cache.get_or_load("b", load, service="search")
    resident = cache.size_bytes
    await cache.get_or_load("big", large, service="search")
    assert cache.size_bytes == resident
    assert (await cache.get_or_load("a", load, service="search"))[1]
    await cache.get_or_load("c", load, service="search")
    assert (await cache.get_or_load("a", load, service="search"))[1]
    assert not (await cache.get_or_load("b", load, service="search"))[1]
    assert cache.size_bytes <= 900


@pytest.mark.asyncio
async def test_expiry_reloads_and_zero_budget_bypasses() -> None:
    now = [0.0]
    cache = MemoryResultCache(4096, clock=lambda: now[0])
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        return {"status": "OK", "value": calls}

    await cache.get_or_load("key", load, service="reverse")
    now[0] = 300.0
    value, hit = await cache.get_or_load("key", load, service="reverse")
    assert not hit and value["value"] == 2
    disabled = MemoryResultCache(0)
    await disabled.get_or_load("key", load, service="reverse")
    await disabled.get_or_load("key", load, service="reverse")
    assert calls == 4 and disabled.size_bytes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"status": "NOT_FOUND"},
    {"status": "ERROR"},
    {"status": "OK", "candidates": [{"geometry_error": {"code": "timeout"}}]},
])
async def test_errors_and_degraded_geometry_are_not_stored(payload) -> None:
    cache = MemoryResultCache(4096)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        return payload

    await cache.get_or_load("key", load, service="geocode")
    await cache.get_or_load("key", load, service="geocode")
    assert calls == 2 and cache.size_bytes == 0


@pytest.mark.asyncio
async def test_concurrent_identical_loads_run_once_and_return_distinct_payloads() -> None:
    cache = MemoryResultCache(4096)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def load():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"status": "OK", "nested": {"value": 1}}

    requests = [asyncio.create_task(cache.get_or_load("key", load, service="geocode"))
                for _ in range(32)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*requests)
    assert calls == 1
    assert sum(hit for _, hit in results) == 31
    results[0][0]["nested"]["value"] = 99
    assert all(value["nested"]["value"] == 1 for value, _ in results[1:])


@pytest.mark.asyncio
async def test_cancelling_one_waiter_keeps_the_shared_load_for_others() -> None:
    cache = MemoryResultCache(4096)
    started = asyncio.Event()
    release = asyncio.Event()

    async def load():
        started.set()
        await release.wait()
        return {"status": "OK"}

    first = asyncio.create_task(cache.get_or_load("key", load, service="reverse"))
    await started.wait()
    second = asyncio.create_task(cache.get_or_load("key", load, service="reverse"))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert (await second)[0] == {"status": "OK"}


@pytest.mark.asyncio
async def test_last_cancelled_waiter_cancels_db_work_and_next_request_can_retry() -> None:
    cache = MemoryResultCache(4096)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def load():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    request = asyncio.create_task(cache.get_or_load("key", load, service="reverse"))
    await started.wait()
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    await asyncio.wait_for(stopped.wait(), timeout=1)

    async def retry():
        return {"status": "OK", "value": "retry"}

    value, hit = await cache.get_or_load("key", retry, service="reverse")
    assert value["value"] == "retry" and not hit


@pytest.mark.asyncio
async def test_clear_during_load_does_not_publish_old_generation() -> None:
    cache = MemoryResultCache(4096)
    started = asyncio.Event()
    release = asyncio.Event()

    async def old():
        started.set()
        await release.wait()
        return {"status": "OK", "value": "old"}

    async def new():
        return {"status": "OK", "value": "new"}

    first = asyncio.create_task(cache.get_or_load("key", old, service="search"))
    await started.wait()
    cache.clear()
    assert (await cache.get_or_load("key", new, service="search"))[0]["value"] == "new"
    release.set()
    assert (await first)[0]["value"] == "old"
    assert (await cache.get_or_load("key", new, service="search"))[0]["value"] == "new"


@pytest.mark.asyncio
async def test_failed_shared_load_is_not_cached_and_close_releases_tasks() -> None:
    cache = MemoryResultCache(4096)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fail():
        started.set()
        await release.wait()
        raise RuntimeError("injected load failure")

    requests = [asyncio.create_task(cache.get_or_load("key", fail, service="search"))
                for _ in range(8)]
    await started.wait()
    release.set()
    outcomes = await asyncio.gather(*requests, return_exceptions=True)
    assert all(isinstance(value, RuntimeError) for value in outcomes)
    assert cache.size_bytes == 0
    await cache.aclose()
    assert not cache._tasks


@pytest.mark.asyncio
async def test_many_unique_inflight_keys_are_bounded_and_excess_load_bypasses() -> None:
    cache = MemoryResultCache(1_000_000)
    release = asyncio.Event()
    started = 0
    all_started = asyncio.Event()

    async def blocked():
        nonlocal started
        started += 1
        if started == 128:
            all_started.set()
        await release.wait()
        return {"status": "OK"}

    requests = [asyncio.create_task(cache.get_or_load(str(i), blocked, service="search"))
                for i in range(128)]
    await asyncio.wait_for(all_started.wait(), timeout=1)

    async def immediate():
        return {"status": "OK", "value": "bypass"}

    value, hit = await cache.get_or_load("extra", immediate, service="search")
    assert value["value"] == "bypass" and not hit
    assert len(cache._tasks) == 128
    release.set()
    await asyncio.gather(*requests)
    await cache.aclose()


@pytest.mark.asyncio
async def test_close_cancels_active_shared_work_and_all_waiters() -> None:
    cache = MemoryResultCache(4096)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def blocked():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    requests = [asyncio.create_task(cache.get_or_load("key", blocked, service="reverse"))
                for _ in range(2)]
    await started.wait()
    await cache.aclose()
    outcomes = await asyncio.gather(*requests, return_exceptions=True)
    assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)
    assert stopped.is_set() and cache.size_bytes == 0
    assert not cache._tasks and not cache._flights
