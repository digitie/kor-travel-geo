"""Process-local cache of the active release's dataset stamp (T-325b, ADR-069 D7).

``AsyncAddressClient`` reads the stamp once per lookup and uses that one value both for the
``dataset`` field of the v2 response and inside the ``geo_cache`` key, so a cached answer is
only ever served under the release it was computed for (ADR-069 구현 기록 — H2). The ledger is
read at most once per ``ttl_s`` per process; failures are remembered for ``failure_ttl_s`` so
concurrent requests do not queue behind a failing read (M5).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from kortravelgeo.dto.v2 import DatasetRef

_LOGGER = logging.getLogger(__name__)

DATASET_REF_TTL_S = 10.0
DATASET_REF_FAILURE_TTL_S = 1.0

DatasetRefLoader = Callable[[], Awaitable[tuple[str, str | None] | None]]


class DatasetRefCache:
    """TTL cache of the active release's ``DatasetRef`` (clock injectable)."""

    def __init__(
        self,
        *,
        ttl_s: float = DATASET_REF_TTL_S,
        failure_ttl_s: float = DATASET_REF_FAILURE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_s = ttl_s
        self._failure_ttl_s = failure_ttl_s
        self._clock = clock
        self._value: DatasetRef | None = None
        self._expires_at = float("-inf")
        self._lock = asyncio.Lock()

    async def get(self, loader: DatasetRefLoader) -> DatasetRef | None:
        if self._clock() < self._expires_at:
            return self._value
        async with self._lock:
            # A waiter that queued behind a load (successful or failed) takes its result.
            if self._clock() < self._expires_at:
                return self._value
            try:
                pair = await loader()
            except Exception:
                # The stamp is metadata: a ledger read failure must not fail the lookup itself.
                _LOGGER.warning("dataset ref lookup failed; omitting dataset", exc_info=True)
                self._value = None
                self._expires_at = self._clock() + self._failure_ttl_s
                return None
            self._value = (
                None if pair is None else DatasetRef(version_token=pair[0], data_token=pair[1])
            )
            self._expires_at = self._clock() + self._ttl_s
            return self._value
