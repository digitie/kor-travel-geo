"""Loader for 도로명주소 출입구 정보 direct entrance files."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.exceptions import LoaderError
from kraddr.geo.loaders.manifest import infer_yyyymm, sha256_file

from .common import TextSource, as_int, discover_text_sources, iter_pipe_rows, required
from .juso_hangul_loader import _alchemy_to_libpq

ProgressCallback = Callable[[float], None]

ROADADDR_ENTRANCE_PATTERN = "RNENTDATA_*.txt"
_RNENT_YYMM_RE = re.compile(r"RNENTDATA_(\d{2})(0[1-9]|1[0-2])_")


@dataclass(frozen=True, slots=True)
class RoadAddrEntranceRow:
    bd_mgt_sn: str
    bjd_cd: str
    ctp_kor_nm: str | None
    sig_kor_nm: str | None
    emd_kor_nm: str | None
    li_kor_nm: str | None
    sig_cd: str
    rn_cd: str
    rn: str | None
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    zip_no: str | None
    notice_de: str | None
    raw_col_13: str | None
    ent_man_no: int | None
    ent_source_cd: str
    ent_detail_cd: str
    x_5179: float
    y_5179: float
    source_file: str
    source_yyyymm: str | None

    @property
    def rncode_full(self) -> str:
        return f"{self.sig_cd}{self.rn_cd}"


@dataclass(frozen=True, slots=True)
class RoadAddrEntranceLoadResult:
    source_count: int
    processed_rows: int
    upserted_rows: int
    source_yyyymm: str | None


def discover_roadaddr_entrance_sources(path: Path | str) -> tuple[TextSource, ...]:
    root = Path(path)
    if root.is_dir():
        sources: list[TextSource] = list(
            discover_text_sources(root, pattern=ROADADDR_ENTRANCE_PATTERN)
        )
        for archive in sorted(root.glob("*.zip")):
            sources.extend(discover_text_sources(archive, pattern=ROADADDR_ENTRANCE_PATTERN))
        return tuple(sorted(sources, key=lambda source: (source.path.name, source.name)))
    return discover_text_sources(root, pattern=ROADADDR_ENTRANCE_PATTERN)


def parse_roadaddr_entrance_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> RoadAddrEntranceRow:
    bd_mgt_sn = required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    bjd_cd = required(row[1], field="bjd_cd", source_name=source_name, line_no=line_no)
    rncode_full = required(row[6], field="rncode_full", source_name=source_name, line_no=line_no)
    if len(rncode_full) != 12 or not rncode_full.isdigit():
        msg = f"{source_name}:{line_no} rncode_full must be a 12-digit string"
        raise LoaderError(msg)
    ent_man_no = _optional_int(
        row[14],
        field="ent_man_no",
        source_name=source_name,
        line_no=line_no,
    )
    return RoadAddrEntranceRow(
        bd_mgt_sn=bd_mgt_sn,
        bjd_cd=bjd_cd,
        ctp_kor_nm=row[2] or None,
        sig_kor_nm=row[3] or None,
        emd_kor_nm=row[4] or None,
        li_kor_nm=row[5] or None,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        rn=row[7] or None,
        buld_se_cd=row[8] or None,
        buld_mnnm=as_int(row[9]),
        buld_slno=as_int(row[10]),
        zip_no=row[11] or None,
        notice_de=row[12] or None,
        raw_col_13=row[13] or None,
        ent_man_no=ent_man_no,
        ent_source_cd=required(
            row[15],
            field="ent_source_cd",
            source_name=source_name,
            line_no=line_no,
        ),
        ent_detail_cd=required(
            row[16],
            field="ent_detail_cd",
            source_name=source_name,
            line_no=line_no,
        ),
        x_5179=_required_float(row[17], field="x_5179", source_name=source_name, line_no=line_no),
        y_5179=_required_float(row[18], field="y_5179", source_name=source_name, line_no=line_no),
        source_file=source_name,
        source_yyyymm=source_yyyymm,
    )


def iter_roadaddr_entrance_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[RoadAddrEntranceRow]:
    yielded = 0
    effective_yyyymm = source_yyyymm or _infer_rnent_yyyymm(source.name)
    for line_no, row in iter_pipe_rows(source, min_columns=19):
        if not _has_real_5179_coordinates(row[17], row[18]):
            continue
        if limit is not None and yielded >= limit:
            return
        yielded += 1
        yield parse_roadaddr_entrance_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_yyyymm=effective_yyyymm,
        )


async def load_roadaddr_entrances(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None = None,
    limit_per_file: int | None = None,
    replace: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> RoadAddrEntranceLoadResult:
    sources = discover_roadaddr_entrance_sources(path)
    if not sources:
        msg = f"road address entrance source contains no {ROADADDR_ENTRANCE_PATTERN}: {path}"
        raise LoaderError(msg)
    effective_yyyymm = source_yyyymm or _infer_common_yyyymm(sources) or infer_yyyymm(path)
    rows = _iter_many(sources, source_yyyymm=effective_yyyymm, limit_per_file=limit_per_file)
    return await copy_roadaddr_entrance_rows(
        engine,
        rows,
        source_path=Path(path),
        source_count=len(sources),
        source_checksum=_source_checksum(sources),
        source_yyyymm=effective_yyyymm,
        replace=replace,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_roadaddr_entrance_rows(
    engine: AsyncEngine,
    rows: Iterable[RoadAddrEntranceRow],
    *,
    source_path: Path,
    source_count: int,
    source_checksum: str,
    source_yyyymm: str | None,
    replace: bool,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> RoadAddrEntranceLoadResult:
    processed_rows = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
CREATE TEMP TABLE _roadaddr_entrc_staging (
  LIKE tl_roadaddr_entrc INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            await cur.execute(
                "ALTER TABLE _roadaddr_entrc_staging ADD COLUMN staging_seq BIGSERIAL"
            )
            async with cur.copy(
                """
COPY _roadaddr_entrc_staging
(bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, sig_cd, rn_cd,
 rn, buld_se_cd, buld_mnnm, buld_slno, zip_no, notice_de, raw_col_13, ent_man_no,
 ent_source_cd, ent_detail_cd, geom, source_file, source_yyyymm)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("roadaddr_entrance_loader cancelled")
                    await copy.write_row(_copy_tuple(row))
                    processed_rows += 1
                    if on_progress and processed_rows % 10_000 == 0:
                        on_progress(0.0)
            if replace:
                await cur.execute("TRUNCATE TABLE tl_roadaddr_entrc")
            upserted_rows = await _upsert_latest_rows(cur, fallback_rowcount=processed_rows)
            await _upsert_manifest(
                cur,
                source_path=source_path,
                source_count=source_count,
                processed_rows=processed_rows,
                upserted_rows=upserted_rows,
                source_checksum=source_checksum,
                source_yyyymm=source_yyyymm,
            )
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return RoadAddrEntranceLoadResult(
        source_count=source_count,
        processed_rows=processed_rows,
        upserted_rows=upserted_rows,
        source_yyyymm=source_yyyymm,
    )


def _copy_tuple(row: RoadAddrEntranceRow) -> tuple[object, ...]:
    return (
        row.bd_mgt_sn,
        row.bjd_cd,
        row.ctp_kor_nm,
        row.sig_kor_nm,
        row.emd_kor_nm,
        row.li_kor_nm,
        row.sig_cd,
        row.rn_cd,
        row.rn,
        row.buld_se_cd,
        row.buld_mnnm,
        row.buld_slno,
        row.zip_no,
        row.notice_de,
        row.raw_col_13,
        row.ent_man_no,
        row.ent_source_cd,
        row.ent_detail_cd,
        f"SRID=5179;POINT({row.x_5179} {row.y_5179})",
        row.source_file,
        row.source_yyyymm,
    )


async def _upsert_latest_rows(cur: psycopg.AsyncCursor[Any], *, fallback_rowcount: int) -> int:
    await cur.execute(
        """
WITH latest AS (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, sig_cd, rn_cd,
         rn, buld_se_cd, buld_mnnm, buld_slno, zip_no, notice_de, raw_col_13, ent_man_no,
         ent_source_cd, ent_detail_cd, geom, source_file, source_yyyymm
    FROM _roadaddr_entrc_staging
   ORDER BY bd_mgt_sn, source_yyyymm DESC NULLS LAST, source_file DESC,
            staging_seq DESC
)
INSERT INTO tl_roadaddr_entrc AS t (
  bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, sig_cd, rn_cd,
  rn, buld_se_cd, buld_mnnm, buld_slno, zip_no, notice_de, raw_col_13, ent_man_no,
  ent_source_cd, ent_detail_cd, geom, source_file, source_yyyymm
)
SELECT bd_mgt_sn, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, sig_cd, rn_cd,
       rn, buld_se_cd, buld_mnnm, buld_slno, zip_no, notice_de, raw_col_13, ent_man_no,
       ent_source_cd, ent_detail_cd, geom, source_file, source_yyyymm
  FROM latest
ON CONFLICT (bd_mgt_sn) DO UPDATE SET
  bjd_cd = EXCLUDED.bjd_cd,
  ctp_kor_nm = EXCLUDED.ctp_kor_nm,
  sig_kor_nm = EXCLUDED.sig_kor_nm,
  emd_kor_nm = EXCLUDED.emd_kor_nm,
  li_kor_nm = EXCLUDED.li_kor_nm,
  sig_cd = EXCLUDED.sig_cd,
  rn_cd = EXCLUDED.rn_cd,
  rn = EXCLUDED.rn,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  zip_no = EXCLUDED.zip_no,
  notice_de = EXCLUDED.notice_de,
  raw_col_13 = EXCLUDED.raw_col_13,
  ent_man_no = EXCLUDED.ent_man_no,
  ent_source_cd = EXCLUDED.ent_source_cd,
  ent_detail_cd = EXCLUDED.ent_detail_cd,
  geom = EXCLUDED.geom,
  source_file = EXCLUDED.source_file,
  source_yyyymm = EXCLUDED.source_yyyymm,
  loaded_at = now()
"""
    )
    return cur.rowcount if cur.rowcount >= 0 else fallback_rowcount


async def _upsert_manifest(
    cur: psycopg.AsyncCursor[Any],
    *,
    source_path: Path,
    source_count: int,
    processed_rows: int,
    upserted_rows: int,
    source_checksum: str,
    source_yyyymm: str | None,
) -> None:
    source_set = {
        "kind": "roadaddr_entrance_full",
        "source_count": source_count,
        "processed_rows": processed_rows,
        "upserted_rows": upserted_rows,
    }
    await cur.execute(
        """
INSERT INTO load_manifest (
  table_name, last_full_load_at, row_count, source_zip, source_checksum,
  source_yyyymm, source_set, updated_at
) VALUES (
  'tl_roadaddr_entrc', now(), %s, %s, %s, %s, %s::jsonb, now()
)
ON CONFLICT (table_name) DO UPDATE SET
  last_full_load_at = EXCLUDED.last_full_load_at,
  row_count = EXCLUDED.row_count,
  source_zip = EXCLUDED.source_zip,
  source_checksum = EXCLUDED.source_checksum,
  source_yyyymm = EXCLUDED.source_yyyymm,
  source_set = EXCLUDED.source_set,
  updated_at = now()
""",
        (
            processed_rows,
            str(source_path),
            source_checksum,
            source_yyyymm,
            json.dumps(source_set, ensure_ascii=False, sort_keys=True),
        ),
    )


def _iter_many(
    sources: Iterable[TextSource],
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None,
) -> Iterator[RoadAddrEntranceRow]:
    for source in sources:
        yield from iter_roadaddr_entrance_rows(
            source,
            source_yyyymm=source_yyyymm,
            limit=limit_per_file,
        )


def _has_real_5179_coordinates(x_raw: str, y_raw: str) -> bool:
    if not x_raw or not y_raw:
        return False
    try:
        x = float(x_raw)
        y = float(y_raw)
    except ValueError:
        return True
    return x != 0.0 and y != 0.0


def _required_float(value: str | None, *, field: str, source_name: str, line_no: int) -> float:
    raw = required(value, field=field, source_name=source_name, line_no=line_no)
    try:
        return float(raw)
    except ValueError as exc:
        msg = f"{source_name}:{line_no} {field} must be a float"
        raise LoaderError(msg) from exc


def _optional_int(value: str, *, field: str, source_name: str, line_no: int) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        msg = f"{source_name}:{line_no} {field} must be an integer"
        raise LoaderError(msg) from exc


def _infer_common_yyyymm(sources: Iterable[TextSource]) -> str | None:
    values = {value for source in sources if (value := _infer_rnent_yyyymm(source.name))}
    return values.pop() if len(values) == 1 else None


def _infer_rnent_yyyymm(source_name: str) -> str | None:
    match = _RNENT_YYMM_RE.search(source_name)
    return f"20{match.group(1)}{match.group(2)}" if match else None


def _source_checksum(sources: Iterable[TextSource]) -> str:
    digest = hashlib.sha256()
    seen: set[Path] = set()
    for source in sorted(sources, key=lambda item: (str(item.path), item.member_name or "")):
        if source.path in seen:
            continue
        seen.add(source.path)
        digest.update(source.path.name.encode())
        digest.update(b"\0")
        digest.update(sha256_file(source.path).encode())
        digest.update(b"\0")
    return digest.hexdigest()
