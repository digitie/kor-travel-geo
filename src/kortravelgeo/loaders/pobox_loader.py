"""epost postal box loader."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.epost_validation import (
    BD_MGT_SN_ALIASES,
    POBOX_KIND_ALIASES,
    POBOX_NAME_ALIASES,
    POBOX_NO_MN_ALIASES,
    POBOX_NO_SL_ALIASES,
    ZIP_NO_ALIASES,
    ensure_postal_validation_passed,
    epost_row_value,
    iter_epost_dict_rows,
    normalize_pobox_kind,
    validate_pobox_file,
)
from kortravelgeo.loaders.text.juso_hangul_loader import _alchemy_to_libpq

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
    for index, row in enumerate(iter_epost_dict_rows(path), start=1):
        zip_no = epost_row_value(row, ZIP_NO_ALIASES)
        if not zip_no:
            continue
        raw_kind = epost_row_value(row, POBOX_KIND_ALIASES)
        pobox_kind = normalize_pobox_kind(raw_kind)
        if pobox_kind is None:
            msg = f"invalid pobox_kind in epost pobox file: {raw_kind}"
            raise LoaderError(msg)
        bd_mgt_sn = epost_row_value(row, BD_MGT_SN_ALIASES) or f"pobox:{index}"
        yield PoboxRow(
            bd_mgt_sn=bd_mgt_sn,
            zip_no=zip_no,
            rn_code=epost_row_value(row, ("rn_code", "도로명코드")),
            pobox_kind=pobox_kind,
            pobox_name=epost_row_value(row, POBOX_NAME_ALIASES),
            pobox_no_mn=_to_int(epost_row_value(row, POBOX_NO_MN_ALIASES)),
            pobox_no_sl=_to_int(epost_row_value(row, POBOX_NO_SL_ALIASES)),
            si_nm=epost_row_value(row, ("si_nm", "시도")),
            sgg_nm=epost_row_value(row, ("sgg_nm", "시군구")),
            emd_nm=epost_row_value(row, ("emd_nm", "읍면동")),
            bjd_cd=epost_row_value(row, ("bjd_cd", "법정동코드")),
        )


async def load_pobox(
    engine: AsyncEngine,
    path: Path | str,
    *,
    validate: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    if validate:
        ensure_postal_validation_passed(validate_pobox_file(path))
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
