"""Loader for 도로명주소 한글_전체분 (``tl_juso_text``)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.pnu import build_pnu

from .common import TextSource, as_int, discover_text_sources, iter_pipe_rows, required

ProgressCallback = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class JusoTextRow:
    bd_mgt_sn: str
    sig_cd: str
    rn_cd: str
    ctp_kor_nm: str | None
    sig_kor_nm: str | None
    emd_kor_nm: str | None
    li_kor_nm: str | None
    bjd_cd: str
    adm_cd: str | None
    adm_kor_nm: str | None
    rn: str | None
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    buld_nm: str | None
    mntn_yn: str | None
    lnbr_mnnm: int | None
    lnbr_slno: int | None
    zip_no: str | None
    source_file: str
    source_yyyymm: str | None

    @property
    def rncode_full(self) -> str:
        return f"{self.sig_cd}{self.rn_cd}"

    @property
    def pnu(self) -> str | None:
        return build_pnu(
            bjd_cd=self.bjd_cd,
            mntn_yn=self.mntn_yn,
            lnbr_mnnm=self.lnbr_mnnm,
            lnbr_slno=self.lnbr_slno,
        )


def juso_text_copy_tuple(row: JusoTextRow) -> tuple[object, ...]:
    return (
        row.bd_mgt_sn,
        row.sig_cd,
        row.rn_cd,
        row.ctp_kor_nm,
        row.sig_kor_nm,
        row.emd_kor_nm,
        row.li_kor_nm,
        row.bjd_cd,
        row.adm_cd,
        row.adm_kor_nm,
        row.rn,
        row.buld_se_cd,
        row.buld_mnnm,
        row.buld_slno,
        row.buld_nm,
        row.mntn_yn,
        row.lnbr_mnnm,
        row.lnbr_slno,
        row.zip_no,
        row.source_file,
        row.source_yyyymm,
    )


def discover_juso_hangul_files(path: Path | str) -> tuple[TextSource, ...]:
    return discover_text_sources(path, pattern="rnaddrkor_*.txt")


def parse_juso_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> JusoTextRow:
    bd_mgt_sn = required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    bjd_cd = required(row[1], field="bjd_cd", source_name=source_name, line_no=line_no)
    rncode_full = required(row[9], field="rncode_full", source_name=source_name, line_no=line_no)
    return JusoTextRow(
        bd_mgt_sn=bd_mgt_sn,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        ctp_kor_nm=row[2] or None,
        sig_kor_nm=row[3] or None,
        emd_kor_nm=row[4] or None,
        li_kor_nm=row[5] or None,
        bjd_cd=bjd_cd,
        adm_cd=row[14] or None,
        adm_kor_nm=row[15] or None,
        rn=row[10] or None,
        buld_se_cd=row[11] or None,
        buld_mnnm=as_int(row[12]),
        buld_slno=as_int(row[13]),
        buld_nm=row[22] or None if len(row) > 22 else None,
        mntn_yn=row[6] or None,
        lnbr_mnnm=as_int(row[7]),
        lnbr_slno=as_int(row[8]),
        zip_no=row[16] or None,
        source_file=source_name,
        source_yyyymm=source_yyyymm,
    )


def iter_juso_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[JusoTextRow]:
    for index, (line_no, row) in enumerate(iter_pipe_rows(source, min_columns=23)):
        if limit is not None and index >= limit:
            return
        yield parse_juso_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_yyyymm=source_yyyymm,
        )


async def load_juso_hangul(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    sources = discover_juso_hangul_files(path)
    rows = _iter_many(sources, source_yyyymm=source_yyyymm, limit_per_file=limit_per_file)
    return await copy_juso_rows(
        engine,
        rows,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_juso_rows(
    engine: AsyncEngine,
    rows: Iterable[JusoTextRow],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    count = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
CREATE TEMP TABLE _juso_text_staging (
  LIKE tl_juso_text INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            async with cur.copy(
                """
COPY _juso_text_staging
(bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
 bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
 mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("juso_hangul_loader cancelled")
                    await copy.write_row(juso_text_copy_tuple(row))
                    count += 1
                    if on_progress and count % 10_000 == 0:
                        on_progress(0.0)
            await cur.execute(
                """
INSERT INTO tl_juso_text AS t (
  bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
  bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
  mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm
)
SELECT bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
       bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
       mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm
  FROM _juso_text_staging
ON CONFLICT (bd_mgt_sn) DO UPDATE SET
  sig_cd = EXCLUDED.sig_cd,
  rn_cd = EXCLUDED.rn_cd,
  ctp_kor_nm = EXCLUDED.ctp_kor_nm,
  sig_kor_nm = EXCLUDED.sig_kor_nm,
  emd_kor_nm = EXCLUDED.emd_kor_nm,
  li_kor_nm = EXCLUDED.li_kor_nm,
  bjd_cd = EXCLUDED.bjd_cd,
  adm_cd = EXCLUDED.adm_cd,
  adm_kor_nm = EXCLUDED.adm_kor_nm,
  rn = EXCLUDED.rn,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  buld_nm = EXCLUDED.buld_nm,
  mntn_yn = EXCLUDED.mntn_yn,
  lnbr_mnnm = EXCLUDED.lnbr_mnnm,
  lnbr_slno = EXCLUDED.lnbr_slno,
  zip_no = EXCLUDED.zip_no,
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
) -> Iterator[JusoTextRow]:
    for source in sources:
        yield from iter_juso_rows(source, source_yyyymm=source_yyyymm, limit=limit_per_file)


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
