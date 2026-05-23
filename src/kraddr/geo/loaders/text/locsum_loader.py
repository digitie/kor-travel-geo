"""Loader for 위치정보요약DB entrance points."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from .common import TextSource, as_int, discover_text_sources, iter_pipe_rows, required
from .juso_hangul_loader import _alchemy_to_libpq

ProgressCallback = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class LocsumEntranceRow:
    sig_cd: str
    ent_man_no: int
    bjd_cd: str
    ctp_kor_nm: str | None
    sig_kor_nm: str | None
    emd_kor_nm: str | None
    rn_cd: str
    rn: str | None
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    zip_no: str | None
    buld_use: str | None
    ent_se_cd: str | None
    adm_kor_nm: str | None
    x_5179: float
    y_5179: float
    source_file: str
    source_yyyymm: str | None

    @property
    def rncode_full(self) -> str:
        return f"{self.sig_cd}{self.rn_cd}"


def discover_locsum_files(path: Path | str) -> tuple[TextSource, ...]:
    return discover_text_sources(path, pattern="entrc_*.txt")


def parse_locsum_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> LocsumEntranceRow:
    sig_cd = required(row[0], field="sig_cd", source_name=source_name, line_no=line_no)
    ent_man_no = as_int(
        required(row[1], field="ent_man_no", source_name=source_name, line_no=line_no)
    )
    rncode_full = required(row[6], field="rncode_full", source_name=source_name, line_no=line_no)
    x = float(required(row[16], field="x_5179", source_name=source_name, line_no=line_no))
    y = float(required(row[17], field="y_5179", source_name=source_name, line_no=line_no))
    assert ent_man_no is not None
    return LocsumEntranceRow(
        sig_cd=sig_cd,
        ent_man_no=ent_man_no,
        bjd_cd=required(row[2], field="bjd_cd", source_name=source_name, line_no=line_no),
        ctp_kor_nm=row[3] or None,
        sig_kor_nm=row[4] or None,
        emd_kor_nm=row[5] or None,
        rn_cd=rncode_full[5:],
        rn=row[7] or None,
        buld_se_cd=row[8] or None,
        buld_mnnm=as_int(row[9]),
        buld_slno=as_int(row[10]),
        zip_no=row[12] or None,
        buld_use=row[13] or None,
        ent_se_cd=row[14] or None,
        adm_kor_nm=row[15] or None,
        x_5179=x,
        y_5179=y,
        source_file=source_name,
        source_yyyymm=source_yyyymm,
    )


def iter_locsum_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[LocsumEntranceRow]:
    yielded = 0
    for line_no, row in iter_pipe_rows(source, min_columns=18):
        if not row[16] or not row[17]:
            continue
        if limit is not None and yielded >= limit:
            return
        yielded += 1
        yield parse_locsum_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_yyyymm=source_yyyymm,
        )


async def load_locsum(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    sources = discover_locsum_files(path)
    rows = _iter_many(sources, source_yyyymm=source_yyyymm, limit_per_file=limit_per_file)
    return await copy_locsum_rows(
        engine,
        rows,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_locsum_rows(
    engine: AsyncEngine,
    rows: Iterable[LocsumEntranceRow],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    count = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
CREATE TEMP TABLE _locsum_staging (
  LIKE tl_locsum_entrc INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            async with cur.copy(
                """
COPY _locsum_staging
(sig_cd, ent_man_no, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, rn_cd, rn,
 buld_se_cd, buld_mnnm, buld_slno, zip_no, buld_use, ent_se_cd, adm_kor_nm,
 geom, source_file, source_yyyymm)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("locsum_loader cancelled")
                    await copy.write_row(
                        (
                            row.sig_cd,
                            row.ent_man_no,
                            row.bjd_cd,
                            row.ctp_kor_nm,
                            row.sig_kor_nm,
                            row.emd_kor_nm,
                            row.rn_cd,
                            row.rn,
                            row.buld_se_cd,
                            row.buld_mnnm,
                            row.buld_slno,
                            row.zip_no,
                            row.buld_use,
                            row.ent_se_cd,
                            row.adm_kor_nm,
                            f"SRID=5179;POINT({row.x_5179} {row.y_5179})",
                            row.source_file,
                            row.source_yyyymm,
                        )
                    )
                    count += 1
                    if on_progress and count % 10_000 == 0:
                        on_progress(0.0)
            await cur.execute(
                """
INSERT INTO tl_locsum_entrc AS t (
  sig_cd, ent_man_no, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, rn_cd, rn,
  buld_se_cd, buld_mnnm, buld_slno, zip_no, buld_use, ent_se_cd, adm_kor_nm,
  geom, source_file, source_yyyymm
)
SELECT sig_cd, ent_man_no, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, rn_cd, rn,
       buld_se_cd, buld_mnnm, buld_slno, zip_no, buld_use, ent_se_cd, adm_kor_nm,
       geom, source_file, source_yyyymm
  FROM _locsum_staging
ON CONFLICT (sig_cd, ent_man_no) DO UPDATE SET
  bjd_cd = EXCLUDED.bjd_cd,
  ctp_kor_nm = EXCLUDED.ctp_kor_nm,
  sig_kor_nm = EXCLUDED.sig_kor_nm,
  emd_kor_nm = EXCLUDED.emd_kor_nm,
  rn_cd = EXCLUDED.rn_cd,
  rn = EXCLUDED.rn,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  zip_no = EXCLUDED.zip_no,
  buld_use = EXCLUDED.buld_use,
  ent_se_cd = EXCLUDED.ent_se_cd,
  adm_kor_nm = EXCLUDED.adm_kor_nm,
  geom = EXCLUDED.geom,
  source_file = EXCLUDED.source_file,
  source_yyyymm = EXCLUDED.source_yyyymm,
  loaded_at = now()
"""
            )
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return count


def _iter_many(
    sources: Iterable[TextSource],
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None,
) -> Iterator[LocsumEntranceRow]:
    for source in sources:
        yield from iter_locsum_rows(source, source_yyyymm=source_yyyymm, limit=limit_per_file)
