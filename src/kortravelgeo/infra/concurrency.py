"""Cross-process PostgreSQL advisory lock helpers."""

from __future__ import annotations

import zlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import KorTravelGeoError


class AdvisoryLockNamespace(IntEnum):
    INIT_DB = 0x4B47_0001
    LOAD_FULL_BATCH = 0x4B47_0010
    LOAD_FULL_SET = 0x4B47_0011
    LOAD_JUSO_TEXT = 0x4B47_0020
    LOAD_DAILY_JUSO = 0x4B47_0021
    LOAD_LOCSUM = 0x4B47_0022
    LOAD_NAVI = 0x4B47_0023
    LOAD_PARCEL_LINK = 0x4B47_0024
    LOAD_DAILY_PARCEL = 0x4B47_0025
    LOAD_SHP_POLYGONS = 0x4B47_0030
    LOAD_SHP_DELTA = 0x4B47_0031
    LOAD_ROADADDR_ENTRANCES = 0x4B47_0040
    LOAD_SPPN_MAKAREA = 0x4B47_0041
    LOAD_POBOX = 0x4B47_0050
    LOAD_BULK = 0x4B47_0051
    LOAD_EPOST = 0x4B47_0052
    UPLOADS_CLEANUP = 0x4B47_0053
    MV_REFRESH = 0x4B47_0060
    BACKUP_CREATE = 0x4B47_0070
    RESTORE_CREATE = 0x4B47_0071
    HOT_SWAP = 0x4B47_0072
    CONSISTENCY_RUN = 0x4B47_0080
    BENCHMARK_QUERY = 0x4B47_0090
    SOURCE_JANITOR = 0x4B47_00A0
    SOURCE_MATCH_ACTIVATE = 0x4B47_00A1
    SOURCE_REBUILD_DB = 0x4B47_00A2
    BACKUP_JANITOR = 0x4B47_00A3
    BACKUP_SCHEDULE = 0x4B47_00A4
    RUNTIME_WARM = 0x4B47_00A5


@dataclass(frozen=True, slots=True)
class AdvisoryLockKey:
    namespace: AdvisoryLockNamespace
    resource_hash: int = 0

    @classmethod
    def for_resource(cls, namespace: AdvisoryLockNamespace, resource: object) -> AdvisoryLockKey:
        raw = str(resource).encode("utf-8")
        return cls(namespace=namespace, resource_hash=zlib.crc32(raw) & 0xFFFF_FFFF)

    @classmethod
    def global_key(cls, namespace: AdvisoryLockNamespace) -> AdvisoryLockKey:
        return cls(namespace=namespace, resource_hash=0)

    def as_int(self) -> int:
        return (int(self.namespace) << 32) | self.resource_hash

    def label(self) -> str:
        return f"{self.namespace.name}:{self.resource_hash:08x}"


class ConcurrentExecutionError(KorTravelGeoError):
    code = "E0409"
    http_status = 409

    def __init__(self, key: AdvisoryLockKey) -> None:
        self.key = key
        super().__init__(
            f"{key.namespace.name} is already running for resource {key.resource_hash:08x}",
            code=self.code,
            http_status=self.http_status,
            hint="기존 작업이 끝난 뒤 다시 시도하세요.",
        )


@asynccontextmanager
async def cross_process_lock(
    engine: AsyncEngine,
    key: AdvisoryLockKey,
) -> AsyncIterator[None]:
    """Acquire a session-level PostgreSQL advisory lock for one operation."""

    async with engine.connect() as conn:
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": key.as_int()},
        )
        await conn.commit()
        if acquired is not True:
            raise ConcurrentExecutionError(key)
        try:
            yield
        finally:
            await conn.scalar(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": key.as_int()},
            )
            await conn.commit()
