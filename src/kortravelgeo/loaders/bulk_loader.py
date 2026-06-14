"""epost bulk-delivery zipcode loader."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.loaders.epost_validation import (
    BD_MGT_SN_ALIASES,
    BULK_NAME_ALIASES,
    DETAIL_ALIASES,
    ZIP_NO_ALIASES,
    ensure_postal_validation_passed,
    epost_row_value,
    iter_epost_dict_rows,
    validate_bulk_file,
)
from kortravelgeo.loaders.text.juso_hangul_loader import _alchemy_to_libpq

ProgressCallback = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class BulkDeliveryRow:
    zip_no: str
    bulk_name: str
    bd_mgt_sn: str | None = None
    detail: str | None = None


def iter_bulk_rows(path: Path | str) -> Iterator[BulkDeliveryRow]:
    for row in iter_epost_dict_rows(path):
        zip_no = epost_row_value(row, ZIP_NO_ALIASES)
        name = epost_row_value(row, BULK_NAME_ALIASES)
        if not zip_no or not name:
            continue
        yield BulkDeliveryRow(
            zip_no=zip_no,
            bulk_name=name,
            bd_mgt_sn=epost_row_value(row, BD_MGT_SN_ALIASES),
            detail=epost_row_value(row, DETAIL_ALIASES),
        )


async def load_bulk_delivery(
    engine: AsyncEngine,
    path: Path | str,
    *,
    validate: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    if validate:
        ensure_postal_validation_passed(validate_bulk_file(path))
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
