"""Dataset stamp for the v2 lookup responses (T-325b, ADR-069 D7).

Every ``/v2/{geocode,reverse,search,regions/within-radius}`` answer carries
``dataset: {version_token, data_token}`` of the active release. The pair is read through a
small per-process cache (TTL 10 s) so the four hot endpoints do not each add a ledger query.
This is unrelated to the ``geo_cache`` result cache: the stamp is attached when the response
is assembled, so a ``geo_cache`` hit also carries the *current* token (ADR-069 D6/D7).

The dependency resolves before the handler runs, so a release activated mid-request yields
the older token on an answer that may already reflect newer data — the safe direction for a
consumer ("old token ⇒ redo").
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Depends, Request

from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.v2 import DatasetRef
from kortravelgeo.infra.admin_repo import AdminRepository

_LOGGER = logging.getLogger(__name__)

DATASET_REF_TTL_S = 10.0

DatasetRefLoader = Callable[[], Awaitable[tuple[str, str | None] | None]]


class DatasetRefCache:
    """Process-local TTL cache of the active release's ``DatasetRef`` (clock injectable)."""

    def __init__(
        self,
        *,
        ttl_s: float = DATASET_REF_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._value: DatasetRef | None = None
        self._expires_at = float("-inf")
        self._lock = asyncio.Lock()

    async def get(self, loader: DatasetRefLoader) -> DatasetRef | None:
        if self._clock() < self._expires_at:
            return self._value
        async with self._lock:
            if self._clock() < self._expires_at:
                return self._value
            try:
                pair = await loader()
            except Exception:
                # The stamp is metadata: a ledger read failure must not fail the lookup itself.
                # Not cached, so the next request retries.
                _LOGGER.warning("dataset ref lookup failed; omitting dataset", exc_info=True)
                return None
            self._value = (
                None if pair is None else DatasetRef(version_token=pair[0], data_token=pair[1])
            )
            self._expires_at = self._clock() + self._ttl_s
            return self._value


def _cache_for(request: Request) -> DatasetRefCache:
    cache = getattr(request.app.state, "dataset_ref_cache", None)
    if not isinstance(cache, DatasetRefCache):
        cache = DatasetRefCache()
        request.app.state.dataset_ref_cache = cache
    return cache


async def get_dataset_ref(
    request: Request,
    client: AsyncAddressClient = Depends(get_client),
) -> DatasetRef | None:
    async def load() -> tuple[str, str | None] | None:
        return await AdminRepository(client._engine()).current_dataset_ref()

    return await _cache_for(request).get(load)
