"""Small raw-SQL repository for ``geo_cache`` result rows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

CACHE_KEY_SCHEMA_VERSION = 1


def make_cache_key(service: str, params: Mapping[str, Any]) -> str:
    """Build a deterministic opaque key without storing raw address text in the key."""

    body = {
        "schema": CACHE_KEY_SCHEMA_VERSION,
        "service": service,
        "params": params,
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"{service}:v{CACHE_KEY_SCHEMA_VERSION}:{hashlib.sha256(encoded).hexdigest()}"


class GeoCacheRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def get_json(self, cache_key: str) -> dict[str, Any] | None:
        """Return a non-expired payload and count the lookup as a hit."""

        async with self.engine.begin() as conn:
            payload = await conn.scalar(
                text(
                    """
UPDATE geo_cache
   SET hit_count = hit_count + 1,
       last_hit_at = now()
 WHERE cache_key = :cache_key
   AND expires_at > now()
RETURNING payload
"""
                ),
                {"cache_key": cache_key},
            )
        return payload if isinstance(payload, dict) else None

    async def set_json(
        self,
        *,
        cache_key: str,
        service: str,
        payload: Mapping[str, Any],
        ttl_days: int,
    ) -> None:
        stmt = text(
            """
INSERT INTO geo_cache (cache_key, service, payload, expires_at)
VALUES (:cache_key, :service, :payload, now() + (:ttl_days * interval '1 day'))
ON CONFLICT (cache_key) DO UPDATE
   SET service = EXCLUDED.service,
       payload = EXCLUDED.payload,
       hit_count = 0,
       last_hit_at = NULL,
       created_at = now(),
       expires_at = EXCLUDED.expires_at
"""
        ).bindparams(bindparam("payload", type_=JSONB))
        async with self.engine.begin() as conn:
            await conn.execute(
                stmt,
                {
                    "cache_key": cache_key,
                    "service": service,
                    "payload": dict(payload),
                    "ttl_days": ttl_days,
                },
            )

    async def clear(self) -> int:
        async with self.engine.begin() as conn:
            result = await conn.execute(text("DELETE FROM geo_cache"))
        return int(result.rowcount or 0)
