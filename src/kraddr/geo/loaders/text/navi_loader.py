"""Loader for 내비게이션용DB centroid and entrance files."""

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

KIND_CODE_MAP = {
    "01": "navi",
    "02": "vehicle",
    "03": "parcel",
}


@dataclass(frozen=True, slots=True)
class NaviBuildingRow:
    bjd_cd: str
    ctp_kor_nm: str | None
    sig_kor_nm: str | None
    emd_kor_nm: str | None
    sig_cd: str
    rn_cd: str
    rn: str | None
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    zip_no: str | None
    bd_mgt_sn: str
    buld_nm: str | None
    buld_use: str | None
    adm_cd: str | None
    adm_kor_nm: str | None
    centroid_x: float
    centroid_y: float
    entrance_x: float | None
    entrance_y: float | None
    source_file: str
    source_yyyymm: str | None


@dataclass(frozen=True, slots=True)
class NaviEntranceRow:
    sig_cd: str
    entry_no: int
    rn_cd: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    bjd_cd: str | None
    kind: str
    x_5179: float
    y_5179: float
    source_file: str
    source_yyyymm: str | None


def discover_navi_build_files(path: Path | str) -> tuple[TextSource, ...]:
    return discover_text_sources(path, pattern="match_build_*.txt")


def discover_navi_entrance_files(path: Path | str) -> tuple[TextSource, ...]:
    return discover_text_sources(path, pattern="match_rs_entrc.txt")


def parse_navi_build_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> NaviBuildingRow:
    rncode_full = required(row[4], field="rncode_full", source_name=source_name, line_no=line_no)
    bd_mgt_sn = required(row[10], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    centroid_x = float(
        required(row[23], field="centroid_x", source_name=source_name, line_no=line_no)
    )
    centroid_y = float(
        required(row[24], field="centroid_y", source_name=source_name, line_no=line_no)
    )
    return NaviBuildingRow(
        bjd_cd=required(row[0], field="bjd_cd", source_name=source_name, line_no=line_no),
        ctp_kor_nm=row[1] or None,
        sig_kor_nm=row[2] or None,
        emd_kor_nm=row[3] or None,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        rn=row[5] or None,
        buld_se_cd=row[6] or None,
        buld_mnnm=as_int(row[7]),
        buld_slno=as_int(row[8]),
        zip_no=row[9] or None,
        bd_mgt_sn=bd_mgt_sn,
        buld_nm=row[11] or None,
        buld_use=row[12] or None,
        adm_cd=row[13] or None,
        adm_kor_nm=row[14] or None,
        centroid_x=centroid_x,
        centroid_y=centroid_y,
        entrance_x=float(row[25]) if len(row) > 25 and row[25] else None,
        entrance_y=float(row[26]) if len(row) > 26 and row[26] else None,
        source_file=source_name,
        source_yyyymm=source_yyyymm,
    )


def parse_navi_entrance_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> NaviEntranceRow:
    sig_cd = required(row[0], field="sig_cd", source_name=source_name, line_no=line_no)
    entry_no = as_int(required(row[1], field="entry_no", source_name=source_name, line_no=line_no))
    rncode_full = required(row[2], field="rncode_full", source_name=source_name, line_no=line_no)
    kind = KIND_CODE_MAP.get(row[7], "aux")
    x = float(required(row[8], field="x_5179", source_name=source_name, line_no=line_no))
    y = float(required(row[9], field="y_5179", source_name=source_name, line_no=line_no))
    assert entry_no is not None
    return NaviEntranceRow(
        sig_cd=sig_cd,
        entry_no=entry_no,
        rn_cd=rncode_full[5:],
        buld_se_cd=row[3] or None,
        buld_mnnm=as_int(row[4]),
        buld_slno=as_int(row[5]),
        bjd_cd=row[6] or None,
        kind=kind,
        x_5179=x,
        y_5179=y,
        source_file=source_name,
        source_yyyymm=source_yyyymm,
    )


def iter_navi_build_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[NaviBuildingRow]:
    """Yield valid building centroid rows.

    `limit` applies to rows yielded after coordinate-missing rows are skipped, not to
    raw file rows scanned.
    """
    yielded = 0
    for line_no, row in iter_pipe_rows(source, min_columns=27):
        if not row[23] or not row[24]:
            continue
        if limit is not None and yielded >= limit:
            return
        yielded += 1
        yield parse_navi_build_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_yyyymm=source_yyyymm,
        )


def iter_navi_entrance_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[NaviEntranceRow]:
    """Yield valid entrance rows.

    `limit` applies to rows yielded after coordinate-missing rows are skipped, not to
    raw file rows scanned.
    """
    yielded = 0
    for line_no, row in iter_pipe_rows(source, min_columns=10):
        if not row[8] or not row[9]:
            continue
        if limit is not None and yielded >= limit:
            return
        yielded += 1
        yield parse_navi_entrance_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_yyyymm=source_yyyymm,
        )


async def load_navi(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> tuple[int, int]:
    build_sources = discover_navi_build_files(path)
    entrance_sources = discover_navi_entrance_files(path)
    build_rows = (
        row
        for source in build_sources
        for row in iter_navi_build_rows(source, source_yyyymm=source_yyyymm, limit=limit_per_file)
    )
    entrance_rows = (
        row
        for source in entrance_sources
        for row in iter_navi_entrance_rows(
            source,
            source_yyyymm=source_yyyymm,
            limit=limit_per_file,
        )
    )
    return await copy_navi_rows(
        engine,
        build_rows,
        entrance_rows,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_navi_rows(
    engine: AsyncEngine,
    build_rows: Iterable[NaviBuildingRow],
    entrance_rows: Iterable[NaviEntranceRow],
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> tuple[int, int]:
    build_count = 0
    entrance_count = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
CREATE TEMP TABLE _navi_build_staging (
  LIKE tl_navi_buld_centroid INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            async with cur.copy(
                """
COPY _navi_build_staging
(bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, sig_cd, rn_cd, rn, buld_se_cd,
 buld_mnnm, buld_slno, zip_no, buld_nm, buld_use, adm_cd, adm_kor_nm,
 centroid_5179, source_file, source_yyyymm)
FROM STDIN
"""
            ) as copy:
                for build_row in build_rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("navi_loader cancelled")
                    await copy.write_row(
                        (
                            build_row.bd_mgt_sn,
                            build_row.bjd_cd,
                            build_row.ctp_kor_nm,
                            build_row.sig_kor_nm,
                            build_row.emd_kor_nm,
                            build_row.sig_cd,
                            build_row.rn_cd,
                            build_row.rn,
                            build_row.buld_se_cd,
                            build_row.buld_mnnm,
                            build_row.buld_slno,
                            build_row.zip_no,
                            build_row.buld_nm,
                            build_row.buld_use,
                            build_row.adm_cd,
                            build_row.adm_kor_nm,
                            f"SRID=5179;POINT({build_row.centroid_x} {build_row.centroid_y})",
                            build_row.source_file,
                            build_row.source_yyyymm,
                        )
                    )
                    build_count += 1
            await cur.execute(
                """
INSERT INTO tl_navi_buld_centroid AS t (
  bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, sig_cd, rn_cd, rn, buld_se_cd,
  buld_mnnm, buld_slno, zip_no, buld_nm, buld_use, adm_cd, adm_kor_nm,
  centroid_5179, source_file, source_yyyymm
)
SELECT bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, sig_cd, rn_cd, rn, buld_se_cd,
       buld_mnnm, buld_slno, zip_no, buld_nm, buld_use, adm_cd, adm_kor_nm,
       centroid_5179, source_file, source_yyyymm
  FROM _navi_build_staging
ON CONFLICT (bd_mgt_sn) DO UPDATE SET
  bjd_cd = EXCLUDED.bjd_cd,
  ctp_kor_nm = EXCLUDED.ctp_kor_nm,
  sig_kor_nm = EXCLUDED.sig_kor_nm,
  emd_kor_nm = EXCLUDED.emd_kor_nm,
  sig_cd = EXCLUDED.sig_cd,
  rn_cd = EXCLUDED.rn_cd,
  rn = EXCLUDED.rn,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  zip_no = EXCLUDED.zip_no,
  buld_nm = EXCLUDED.buld_nm,
  buld_use = EXCLUDED.buld_use,
  adm_cd = EXCLUDED.adm_cd,
  adm_kor_nm = EXCLUDED.adm_kor_nm,
  centroid_5179 = EXCLUDED.centroid_5179,
  source_file = EXCLUDED.source_file,
  source_yyyymm = EXCLUDED.source_yyyymm,
  loaded_at = now()
"""
            )
            await cur.execute(
                """
CREATE TEMP TABLE _navi_entrc_staging (
  LIKE tl_navi_entrc INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            async with cur.copy(
                """
COPY _navi_entrc_staging
(sig_cd, entry_no, bjd_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno, kind,
 geom, source_file, source_yyyymm)
FROM STDIN
"""
            ) as copy:
                for entrance_row in entrance_rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("navi_loader cancelled")
                    await copy.write_row(
                        (
                            entrance_row.sig_cd,
                            entrance_row.entry_no,
                            entrance_row.bjd_cd,
                            entrance_row.rn_cd,
                            entrance_row.buld_se_cd,
                            entrance_row.buld_mnnm,
                            entrance_row.buld_slno,
                            entrance_row.kind,
                            f"SRID=5179;POINT({entrance_row.x_5179} {entrance_row.y_5179})",
                            entrance_row.source_file,
                            entrance_row.source_yyyymm,
                        )
                    )
                    entrance_count += 1
            await cur.execute(
                """
INSERT INTO tl_navi_entrc AS t (
  sig_cd, entry_no, bjd_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno, kind,
  geom, source_file, source_yyyymm
)
SELECT sig_cd, entry_no, bjd_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno, kind,
       geom, source_file, source_yyyymm
  FROM _navi_entrc_staging
ON CONFLICT (sig_cd, entry_no) DO UPDATE SET
  bjd_cd = EXCLUDED.bjd_cd,
  rn_cd = EXCLUDED.rn_cd,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  kind = EXCLUDED.kind,
  geom = EXCLUDED.geom,
  source_file = EXCLUDED.source_file,
  source_yyyymm = EXCLUDED.source_yyyymm,
  loaded_at = now()
"""
            )
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return build_count, entrance_count
