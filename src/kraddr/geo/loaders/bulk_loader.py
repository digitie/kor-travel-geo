"""epost bulk-delivery zipcode loader."""

from __future__ import annotations

import asyncio
import csv
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.loaders.text.juso_hangul_loader import _alchemy_to_libpq

ProgressCallback = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class BulkDeliveryRow:
    zip_no: str
    bulk_name: str
    bd_mgt_sn: str | None = None
    detail: str | None = None


def iter_bulk_rows(path: Path | str) -> Iterator[BulkDeliveryRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        for row in reader:
            zip_no = row.get("zip_no") or row.get("우편번호")
            name = row.get("bulk_name") or row.get("다량배달처명") or row.get("기관명")
            if not zip_no or not name:
                continue
            yield BulkDeliveryRow(
                zip_no=zip_no,
                bulk_name=name,
                bd_mgt_sn=row.get("bd_mgt_sn") or row.get("건물관리번호"),
                detail=row.get("detail") or row.get("상세주소"),
            )


async def load_bulk_delivery(
    engine: AsyncEngine,
    path: Path | str,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    return await copy_bulk_rows(
        engine,
        iter_bulk_rows(path),
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_bulk_rows(
    engine: AsyncEngine,
    rows: Iterable[BulkDeliveryRow],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    count = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE postal_bulk_delivery")
            async with cur.copy(
                """
COPY postal_bulk_delivery (zip_no, bd_mgt_sn, bulk_name, detail)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("bulk_loader cancelled")
                    await copy.write_row((row.zip_no, row.bd_mgt_sn, row.bulk_name, row.detail))
                    count += 1
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return count

