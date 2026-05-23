"""epost postal box loader."""

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
class PoboxRow:
    bd_mgt_sn: str
    zip_no: str
    rn_code: str | None
    pobox_kind: str
    pobox_name: str | None
    pobox_no_mn: int | None
    pobox_no_sl: int | None
    si_nm: str | None
    sgg_nm: str | None
    emd_nm: str | None
    bjd_cd: str | None


def iter_pobox_rows(path: Path | str) -> Iterator[PoboxRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="|")
        for index, row in enumerate(reader, start=1):
            zip_no = row.get("zip_no") or row.get("우편번호")
            if not zip_no:
                continue
            bd_mgt_sn = row.get("bd_mgt_sn") or row.get("건물관리번호") or f"pobox:{index}"
            yield PoboxRow(
                bd_mgt_sn=bd_mgt_sn,
                zip_no=zip_no,
                rn_code=row.get("rn_code") or row.get("도로명코드"),
                pobox_kind=(row.get("pobox_kind") or row.get("구분") or "PO"),
                pobox_name=row.get("pobox_name") or row.get("사서함명"),
                pobox_no_mn=_to_int(row.get("pobox_no_mn") or row.get("사서함본번")),
                pobox_no_sl=_to_int(row.get("pobox_no_sl") or row.get("사서함부번")),
                si_nm=row.get("si_nm") or row.get("시도"),
                sgg_nm=row.get("sgg_nm") or row.get("시군구"),
                emd_nm=row.get("emd_nm") or row.get("읍면동"),
                bjd_cd=row.get("bjd_cd") or row.get("법정동코드"),
            )


async def load_pobox(
    engine: AsyncEngine,
    path: Path | str,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    return await copy_pobox_rows(
        engine,
        iter_pobox_rows(path),
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_pobox_rows(
    engine: AsyncEngine,
    rows: Iterable[PoboxRow],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    count = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE postal_pobox")
            async with cur.copy(
                """
COPY postal_pobox
(bd_mgt_sn, zip_no, rn_code, pobox_kind, pobox_name, pobox_no_mn, pobox_no_sl,
 si_nm, sgg_nm, emd_nm, bjd_cd)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("pobox_loader cancelled")
                    await copy.write_row(
                        (
                            row.bd_mgt_sn,
                            row.zip_no,
                            row.rn_code,
                            row.pobox_kind,
                            row.pobox_name,
                            row.pobox_no_mn,
                            row.pobox_no_sl,
                            row.si_nm,
                            row.sgg_nm,
                            row.emd_nm,
                            row.bjd_cd,
                        )
                    )
                    count += 1
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return count


def _to_int(value: str | None) -> int | None:
    return int(value) if value else None

