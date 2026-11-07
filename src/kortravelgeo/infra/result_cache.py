"""Bounded process-local response cache; keys include the serving release and query options."""

from __future__ import annotations

import asyncio
import sys
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import orjson

from .metrics import record_memory_result_cache

CacheService = Literal["geocode", "reverse", "search"]
PayloadLoader = Callable[[], Awaitable[dict[str, Any]]]
_TTL_SECONDS = 300.0
_MAX_IN_FLIGHT = 128
_ENTRY_OVERHEAD_BYTES = 256


@dataclass(frozen=True, slots=True)
class _Entry:
    payload: bytes
    expires_at: float
    weight: int


@dataclass(slots=True)
class _Flight:
    task: asyncio.Task[bytes]
    waiters: int = 0


def _cacheable(payload: dict[str, Any]) -> bool:
    if payload.get("status") != "OK":
        return False
    # A transient optional-geometry timeout must not become a cached degraded answer.
    return not any(
        isinstance(candidate, dict) and candidate.get("geometry_error") is not None
        for candidate in payload.get("candidates", ())
    )


class MemoryResultCache:
    """Byte-budgeted LRU with bounded, cancellation-aware coalescing of identical loads.

    Each result is decoded independently so mutable metadata/GeoJSON cannot leak across
    responses. The counter budget includes the encoded bytes, key and conservative entry
    overhead; normal request/DTO allocations are outside that resident-cache budget.
    """

    def __init__(
        self,
        max_bytes: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_bytes = max_bytes
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._size_bytes = 0
        self._generation = 0
        self._flights: dict[tuple[int, str], _Flight] = {}
        self._tasks: set[asyncio.Task[bytes]] = set()

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def clear(self) -> None:
        self._generation += 1
        self._entries.clear()
        self._size_bytes = 0

    async def aclose(self) -> None:
        self.clear()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def get_or_load(
        self,
        key: str,
        loader: PayloadLoader,
        *,
        service: CacheService,
    ) -> tuple[dict[str, Any], bool]:
        if self._max_bytes == 0:
            record_memory_result_cache(service, "bypass")
            return await loader(), False
        entry = self._entries.get(key)
        if entry is not None:
            if self._clock() < entry.expires_at:
                self._entries.move_to_end(key)
                record_memory_result_cache(service, "hit")
                return self._decode(entry.payload), True
            self._entries.pop(key)
            self._size_bytes -= entry.weight

        flight_key = (self._generation, key)
        flight = self._flights.get(flight_key)
        shared = flight is not None
        if flight is None:
            if len(self._tasks) >= _MAX_IN_FLIGHT:
                record_memory_result_cache(service, "bypass")
                return await loader(), False
            task = asyncio.create_task(self._load(key, loader, self._generation))
            flight = _Flight(task)
            self._flights[flight_key] = flight
            self._tasks.add(task)

            def finished(completed: asyncio.Task[bytes]) -> None:
                self._tasks.discard(completed)
                if self._flights.get(flight_key) is flight:
                    self._flights.pop(flight_key)
                if not completed.cancelled():
                    completed.exception()  # All waiters may have disconnected.

            task.add_done_callback(finished)
        record_memory_result_cache(service, "coalesced" if shared else "miss")
        flight.waiters += 1
        try:
            payload = await asyncio.shield(flight.task)
            return self._decode(payload), shared
        finally:
            flight.waiters -= 1
            if flight.waiters == 0 and not flight.task.done():
                if self._flights.get(flight_key) is flight:
                    self._flights.pop(flight_key)
                flight.task.cancel()

    async def _load(self, key: str, loader: PayloadLoader, generation: int) -> bytes:
        payload = await loader()
        encoded = orjson.dumps(payload)
        weight = sys.getsizeof(key) + sys.getsizeof(encoded) + _ENTRY_OVERHEAD_BYTES
        if generation == self._generation and _cacheable(payload) and weight <= self._max_bytes:
            # orjson's bytes can retain a larger allocation than getsizeof reports.
            # Copy into an exact-sized Python buffer before long-lived retention.
            encoded = bytes(memoryview(encoded))
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._size_bytes -= previous.weight
            while self._entries and self._size_bytes + weight > self._max_bytes:
                _, evicted = self._entries.popitem(last=False)
                self._size_bytes -= evicted.weight
            self._entries[key] = _Entry(encoded, self._clock() + _TTL_SECONDS, weight)
            self._size_bytes += weight
        return encoded

    @staticmethod
    def _decode(payload: bytes) -> dict[str, Any]:
        value: dict[str, Any] = orjson.loads(payload)
        return value
