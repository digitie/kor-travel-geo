"""Public API key persistence."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.admin import (
    PublicApiKeyCreateResponse,
    PublicApiKeyState,
    PublicApiKeySummary,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError

PUBLIC_API_KEY_QUERY_PARAM = "key"
PUBLIC_API_KEY_LENGTH = 32
PUBLIC_API_KEY_ALPHABET = string.ascii_letters + string.digits

_PUBLIC_API_KEY_SELECT = """
SELECT public_api_key_id::text AS public_api_key_id,
       label, key_hint, state, created_at, created_by, revoked_at, revoked_by
  FROM ops.public_api_keys
"""


def generate_public_api_key() -> str:
    """Return a VWorld-style opaque API key value.

    VWorld keys are carried as the ``key`` query parameter. We keep the same
    wire shape and use 32 URL-safe alphanumeric characters so the value is safe
    in query strings without additional encoding.
    """

    return "".join(secrets.choice(PUBLIC_API_KEY_ALPHABET) for _ in range(PUBLIC_API_KEY_LENGTH))


def hash_public_api_key(api_key: str) -> str:
    key = api_key.strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def public_api_key_matches(api_key: str, key_hashes: frozenset[str]) -> bool:
    key_hash = hash_public_api_key(api_key)
    return any(hmac.compare_digest(key_hash, stored_hash) for stored_hash in key_hashes)


class PublicApiKeyRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def list_keys(self, *, limit: int = 100) -> list[PublicApiKeySummary]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_PUBLIC_API_KEY_SELECT + " ORDER BY created_at DESC LIMIT :limit"),
                    {"limit": limit},
                )
            ).mappings().all()
        return [_map_public_api_key(row) for row in rows]

    async def active_key_hashes(self) -> frozenset[str]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT key_hash
  FROM ops.public_api_keys
 WHERE state = 'active'
"""
                    )
                )
            ).scalars().all()
        return frozenset(str(row) for row in rows)

    async def create_key(
        self,
        *,
        label: str | None,
        created_by: str | None,
    ) -> PublicApiKeyCreateResponse:
        normalized_label = label.strip() if label is not None else None
        if normalized_label == "":
            normalized_label = None
        api_key = generate_public_api_key()
        item_id = str(uuid4())
        params = {
            "public_api_key_id": item_id,
            "key_hash": hash_public_api_key(api_key),
            "key_hint": api_key[-6:],
            "label": normalized_label,
            "created_by": created_by,
        }
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
INSERT INTO ops.public_api_keys
  (public_api_key_id, key_hash, key_hint, label, created_by)
VALUES
  (:public_api_key_id, :key_hash, :key_hint, :label, :created_by)
RETURNING public_api_key_id::text AS public_api_key_id,
          label, key_hint, state, created_at, created_by, revoked_at, revoked_by
"""
                    ),
                    params,
                )
            ).mappings().one()
        return PublicApiKeyCreateResponse(key=api_key, item=_map_public_api_key(row))

    async def revoke_key(
        self,
        public_api_key_id: str,
        *,
        revoked_by: str | None,
    ) -> PublicApiKeySummary:
        # The id flows into a UUID column; reject a malformed id as a clean 404 instead of
        # letting Postgres raise 'invalid input syntax for type uuid' (a DBAPIError → 500).
        try:
            UUID(public_api_key_id)
        except ValueError as exc:
            raise NotFoundError(
                f"active public API key not found: {public_api_key_id}"
            ) from exc
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
UPDATE ops.public_api_keys
   SET state = 'revoked',
       revoked_at = now(),
       revoked_by = :revoked_by
 WHERE public_api_key_id = :public_api_key_id
   AND state = 'active'
RETURNING public_api_key_id::text AS public_api_key_id,
          label, key_hint, state, created_at, created_by, revoked_at, revoked_by
"""
                    ),
                    {"public_api_key_id": public_api_key_id, "revoked_by": revoked_by},
                )
            ).mappings().first()
        if row is None:
            raise NotFoundError(f"active public API key not found: {public_api_key_id}")
        return _map_public_api_key(row)


def _map_public_api_key(row: Any) -> PublicApiKeySummary:
    data = dict(row)
    state_value = str(data["state"])
    if state_value not in {"active", "revoked"}:
        raise InvalidInputError(f"invalid public API key state: {state_value}")
    return PublicApiKeySummary(
        public_api_key_id=str(data["public_api_key_id"]),
        label=str(data["label"]) if data.get("label") is not None else None,
        key_hint=str(data["key_hint"]),
        state=cast("PublicApiKeyState", state_value),
        created_at=data["created_at"],
        created_by=str(data["created_by"]) if data.get("created_by") is not None else None,
        revoked_at=data.get("revoked_at"),
        revoked_by=str(data["revoked_by"]) if data.get("revoked_by") is not None else None,
    )
