"""Loader for building-to-parcel link text sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import InvalidInputError, LoaderError
from kortravelgeo.infra.pnu import build_pnu
from kortravelgeo.loaders.manifest import infer_yyyymm, sha256_file
from kortravelgeo.settings import LoadCodeAction, get_settings

from .common import TextSource, as_int, discover_text_sources, iter_pipe_rows, required
from .daily_juso_loader import (
    DAILY_LNBR_PATTERN,
    discover_daily_juso_sources,
    infer_daily_mvmn_de,
    is_no_data_source,
)

ProgressCallback = Callable[[float], None]

JIBUN_RNADDRKOR_PATTERN = "jibun_rnaddrkor_*.txt"


@dataclass(frozen=True, slots=True)
class JusoParcelLinkRow:
    bd_mgt_sn: str
    pnu: str
    bjd_cd: str
    mntn_yn: str
    lnbr_mnnm: int
    lnbr_slno: int
    sig_cd: str
    rn_cd: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    source_kind: str
    source_file: str
    source_yyyymm: str | None
    line_no: int
    mvm_res_cd: str | None = None
    mvmn_de: str | None = None


@dataclass(frozen=True, slots=True)
class JusoParcelLinkLoadResult:
    source_kind: str
    source_count: int
    processed_rows: int
    upsert_candidates: int
    delete_candidates: int
    upserted_rows: int
    deleted_rows: int
    skipped_no_data_sources: int
    last_mvmn_de: str | None
    source_yyyymm: str | None


def discover_jibun_rnaddrkor_files(path: Path | str) -> tuple[TextSource, ...]:
    return discover_text_sources(path, pattern=JIBUN_RNADDRKOR_PATTERN)


def discover_daily_lnbr_sources(path: Path | str) -> tuple[TextSource, ...]:
    return discover_daily_juso_sources(path).lnbr


def iter_jibun_parcel_link_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[JusoParcelLinkRow]:
    for index, (line_no, row) in enumerate(iter_pipe_rows(source, min_columns=14)):
        if limit is not None and index >= limit:
            return
        yield parse_parcel_link_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_kind="jibun_full",
            source_yyyymm=source_yyyymm,
        )


def iter_daily_lnbr_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[JusoParcelLinkRow]:
    if is_no_data_source(source):
        return
    mvmn_de = infer_daily_mvmn_de(source)
    effective_yyyymm = source_yyyymm or (mvmn_de[:6] if mvmn_de else None)
    for index, (line_no, row) in enumerate(iter_pipe_rows(source, min_columns=14)):
        if limit is not None and index >= limit:
            return
        mvm_res_cd = required(
            row[13],
            field="mvm_res_cd",
            source_name=source.name,
            line_no=line_no,
        )
        yield parse_parcel_link_row(
            row,
            source_name=source.name,
            line_no=line_no,
            source_kind="daily_lnbr",
            source_yyyymm=effective_yyyymm,
            mvm_res_cd=mvm_res_cd,
            mvmn_de=mvmn_de,
        )


def parse_parcel_link_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_kind: str,
    source_yyyymm: str | None,
    mvm_res_cd: str | None = None,
    mvmn_de: str | None = None,
) -> JusoParcelLinkRow:
    bd_mgt_sn = required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    bjd_cd = required(row[1], field="bjd_cd", source_name=source_name, line_no=line_no)
    mntn_yn = required(row[6], field="mntn_yn", source_name=source_name, line_no=line_no)
    lnbr_mnnm = _required_int(row[7], field="lnbr_mnnm", source_name=source_name, line_no=line_no)
    lnbr_slno = as_int(row[8]) or 0
    rncode_full = required(row[9], field="rncode_full", source_name=source_name, line_no=line_no)
    if len(rncode_full) != 12 or not rncode_full.isdigit():
        msg = f"{source_name}:{line_no} rncode_full must be a 12-digit string"
        raise LoaderError(msg)
    try:
        pnu = build_pnu(
            bjd_cd=bjd_cd,
            mntn_yn=mntn_yn,
            lnbr_mnnm=lnbr_mnnm,
            lnbr_slno=lnbr_slno,
        )
    except (InvalidInputError, ValueError) as exc:
        msg = f"{source_name}:{line_no} invalid PNU fields: {exc}"
        raise LoaderError(msg) from exc
    if pnu is None:
        msg = f"{source_name}:{line_no} parcel link row cannot build PNU"
        raise LoaderError(msg)
    return JusoParcelLinkRow(
        bd_mgt_sn=bd_mgt_sn,
        pnu=pnu,
        bjd_cd=bjd_cd,
        mntn_yn=mntn_yn,
        lnbr_mnnm=lnbr_mnnm,
        lnbr_slno=lnbr_slno,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        buld_se_cd=row[10] or None,
        buld_mnnm=as_int(row[11]),
        buld_slno=as_int(row[12]),
        source_kind=source_kind,
        source_file=source_name,
        source_yyyymm=source_yyyymm,
        line_no=line_no,
        mvm_res_cd=mvm_res_cd,
        mvmn_de=mvmn_de,
    )


async def load_juso_parcel_link_snapshot(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None = None,
    replace: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> JusoParcelLinkLoadResult:
    sources = discover_jibun_rnaddrkor_files(path)
    if not sources:
        msg = f"jibun parcel link source contains no {JIBUN_RNADDRKOR_PATTERN} files: {path}"
        raise LoaderError(msg)
    effective_yyyymm = source_yyyymm or infer_yyyymm(path)
    rows = _iter_jibun_many(sources, source_yyyymm=effective_yyyymm, limit_per_file=limit_per_file)
    return await copy_juso_parcel_link_snapshot_rows(
        engine,
        rows,
        source_path=Path(path),
        source_count=len(sources),
        source_yyyymm=effective_yyyymm,
        replace=replace,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def load_daily_parcel_link_delta(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None = None,
    code_actions: Mapping[str, LoadCodeAction] | None = None,
    limit_per_file: int | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> JusoParcelLinkLoadResult:
    sources = discover_daily_lnbr_sources(path)
    actions = dict(code_actions or get_settings().mvm_res_code_actions)
    upsert_codes, delete_codes = _action_codes(actions)
    no_data_count = sum(1 for source in sources if is_no_data_source(source))
    last_mvmn_de = _max_mvmn_de(sources)
    rows = _iter_lnbr_many(sources, source_yyyymm=source_yyyymm, limit_per_file=limit_per_file)
    return await copy_daily_parcel_link_delta_rows(
        engine,
        rows,
        source_path=Path(path),
        source_count=len(sources),
        skipped_no_data_sources=no_data_count,
        last_mvmn_de=last_mvmn_de,
        manifest_source_yyyymm=source_yyyymm,
        code_actions=actions,
        upsert_codes=upsert_codes,
        delete_codes=delete_codes,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


async def copy_juso_parcel_link_snapshot_rows(
    engine: AsyncEngine,
    rows: Iterable[JusoParcelLinkRow],
    *,
    source_path: Path,
    source_count: int,
    source_yyyymm: str | None,
    replace: bool,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> JusoParcelLinkLoadResult:
    processed_rows = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await _create_staging_table(cur, with_movement=False)
            async with cur.copy(_parcel_link_copy_sql("_juso_parcel_link_staging")) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("parcel_link_loader cancelled")
                    await copy.write_row(_parcel_link_copy_tuple(row))
                    processed_rows += 1
                    if on_progress and processed_rows % 10_000 == 0:
                        on_progress(0.0)
            if replace:
                await cur.execute("TRUNCATE TABLE tl_juso_parcel_link")
            upserted_rows = await _upsert_latest_rows(cur, fallback_rowcount=processed_rows)
            await _upsert_manifest(
                cur,
                source_path=source_path,
                source_kind="jibun_full",
                processed_rows=processed_rows,
                source_count=source_count,
                skipped_no_data_sources=0,
                upsert_candidates=processed_rows,
                delete_candidates=0,
                upserted_rows=upserted_rows,
                deleted_rows=0,
                last_mvmn_de=None,
                source_yyyymm=source_yyyymm,
                full_load=True,
            )
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return JusoParcelLinkLoadResult(
        source_kind="jibun_full",
        source_count=source_count,
        processed_rows=processed_rows,
        upsert_candidates=processed_rows,
        delete_candidates=0,
        upserted_rows=upserted_rows,
        deleted_rows=0,
        skipped_no_data_sources=0,
        last_mvmn_de=None,
        source_yyyymm=source_yyyymm,
    )


async def copy_daily_parcel_link_delta_rows(
    engine: AsyncEngine,
    rows: Iterable[JusoParcelLinkRow],
    *,
    source_path: Path,
    source_count: int,
    skipped_no_data_sources: int,
    last_mvmn_de: str | None,
    manifest_source_yyyymm: str | None,
    code_actions: Mapping[str, LoadCodeAction],
    upsert_codes: tuple[str, ...],
    delete_codes: tuple[str, ...],
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> JusoParcelLinkLoadResult:
    processed_rows = 0
    upsert_candidates = 0
    delete_candidates = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await _create_staging_table(cur, with_movement=True)
            copy_sql = _parcel_link_copy_sql(
                "_juso_parcel_link_staging",
                with_movement=True,
            )
            async with cur.copy(copy_sql) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("parcel_link_delta_loader cancelled")
                    if row.mvm_res_cd is None:
                        msg = f"{row.source_file}:{row.line_no} missing movement code"
                        raise LoaderError(msg)
                    action = code_actions.get(row.mvm_res_cd)
                    if action is None:
                        msg = (
                            f"{row.source_file}:{row.line_no} unsupported "
                            f"mvm_res_cd={row.mvm_res_cd}"
                        )
                        raise LoaderError(msg)
                    await copy.write_row(
                        (*_parcel_link_copy_tuple(row), row.mvm_res_cd, row.mvmn_de)
                    )
                    processed_rows += 1
                    if action in {"insert", "update"}:
                        upsert_candidates += 1
                    elif action == "delete":
                        delete_candidates += 1
                    if on_progress and processed_rows % 10_000 == 0:
                        on_progress(0.0)
            upserted_rows = await _upsert_latest_rows(
                cur,
                upsert_codes=upsert_codes,
                fallback_rowcount=upsert_candidates,
            )
            deleted_rows = await _delete_latest_rows(
                cur,
                delete_codes=delete_codes,
                fallback_rowcount=delete_candidates,
            )
            effective_yyyymm = manifest_source_yyyymm or (
                last_mvmn_de[:6] if last_mvmn_de else infer_yyyymm(source_path)
            )
            await _upsert_manifest(
                cur,
                source_path=source_path,
                source_kind="daily_lnbr",
                processed_rows=processed_rows,
                source_count=source_count,
                skipped_no_data_sources=skipped_no_data_sources,
                upsert_candidates=upsert_candidates,
                delete_candidates=delete_candidates,
                upserted_rows=upserted_rows,
                deleted_rows=deleted_rows,
                last_mvmn_de=last_mvmn_de,
                source_yyyymm=effective_yyyymm,
                full_load=False,
            )
        await conn.commit()
    if on_progress:
        on_progress(1.0)
    return JusoParcelLinkLoadResult(
        source_kind="daily_lnbr",
        source_count=source_count,
        processed_rows=processed_rows,
        upsert_candidates=upsert_candidates,
        delete_candidates=delete_candidates,
        upserted_rows=upserted_rows,
        deleted_rows=deleted_rows,
        skipped_no_data_sources=skipped_no_data_sources,
        last_mvmn_de=last_mvmn_de,
        source_yyyymm=manifest_source_yyyymm
        or (last_mvmn_de[:6] if last_mvmn_de else infer_yyyymm(source_path)),
    )


def _required_int(value: str | None, *, field: str, source_name: str, line_no: int) -> int:
    raw = required(value, field=field, source_name=source_name, line_no=line_no)
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"{source_name}:{line_no} {field} must be an integer"
        raise LoaderError(msg) from exc


def _iter_jibun_many(
    sources: Iterable[TextSource],
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None,
) -> Iterator[JusoParcelLinkRow]:
    for source in sources:
        yield from iter_jibun_parcel_link_rows(
            source,
            source_yyyymm=source_yyyymm,
            limit=limit_per_file,
        )


def _iter_lnbr_many(
    sources: Iterable[TextSource],
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None,
) -> Iterator[JusoParcelLinkRow]:
    for source in sources:
        yield from iter_daily_lnbr_rows(source, source_yyyymm=source_yyyymm, limit=limit_per_file)


def _max_mvmn_de(sources: Iterable[TextSource]) -> str | None:
    values = [value for source in sources if (value := infer_daily_mvmn_de(source))]
    return max(values) if values else None


def _action_codes(
    code_actions: Mapping[str, LoadCodeAction],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    allowed = {"insert", "update", "delete"}
    invalid = tuple(
        f"{code}:{action}" for code, action in code_actions.items() if action not in allowed
    )
    if invalid:
        msg = f"unsupported mvm_res_cd action mapping: {', '.join(invalid)}"
        raise LoaderError(msg)
    upsert_codes = tuple(
        sorted(code for code, action in code_actions.items() if action in {"insert", "update"})
    )
    delete_codes = tuple(
        sorted(code for code, action in code_actions.items() if action == "delete")
    )
    return upsert_codes, delete_codes


async def _create_staging_table(cur: psycopg.AsyncCursor[Any], *, with_movement: bool) -> None:
    await cur.execute(
        """
CREATE TEMP TABLE _juso_parcel_link_staging (
  LIKE tl_juso_parcel_link INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
    )
    await cur.execute("ALTER TABLE _juso_parcel_link_staging ADD COLUMN mvmn_de TEXT")
    await cur.execute("ALTER TABLE _juso_parcel_link_staging ADD COLUMN staging_seq BIGSERIAL")
    if with_movement:
        await cur.execute(
            "ALTER TABLE _juso_parcel_link_staging ADD COLUMN mvm_res_cd TEXT NOT NULL"
        )


def _parcel_link_copy_sql(table_name: str, *, with_movement: bool = False) -> str:
    movement = ", mvm_res_cd, mvmn_de" if with_movement else ""
    return f"""
COPY {table_name}
(bd_mgt_sn, pnu, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
 sig_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno,
 source_kind, source_file, source_yyyymm, last_mvmn_de{movement})
FROM STDIN
"""


def _parcel_link_copy_tuple(row: JusoParcelLinkRow) -> tuple[object, ...]:
    return (
        row.bd_mgt_sn,
        row.pnu,
        row.bjd_cd,
        row.mntn_yn,
        row.lnbr_mnnm,
        row.lnbr_slno,
        row.sig_cd,
        row.rn_cd,
        row.buld_se_cd,
        row.buld_mnnm,
        row.buld_slno,
        row.source_kind,
        row.source_file,
        row.source_yyyymm,
        row.mvmn_de,
    )


async def _upsert_latest_rows(
    cur: psycopg.AsyncCursor[Any],
    *,
    fallback_rowcount: int,
    upsert_codes: tuple[str, ...] | None = None,
) -> int:
    code_filter = ""
    params: tuple[Any, ...] = ()
    if upsert_codes is not None:
        if not upsert_codes:
            return 0
        code_filter = "WHERE mvm_res_cd = ANY(%s::text[])"
        params = (list(upsert_codes),)
    await cur.execute(
        f"""
WITH latest AS (
  SELECT DISTINCT ON (bd_mgt_sn, pnu)
         bd_mgt_sn, pnu, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
         sig_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno,
         source_kind, source_file, source_yyyymm, last_mvmn_de
    FROM _juso_parcel_link_staging
   {code_filter}
   ORDER BY bd_mgt_sn, pnu, mvmn_de DESC NULLS LAST, source_file DESC, staging_seq DESC
)
INSERT INTO tl_juso_parcel_link AS t (
  bd_mgt_sn, pnu, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
  sig_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno,
  source_kind, source_file, source_yyyymm, last_mvmn_de
)
SELECT bd_mgt_sn, pnu, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
       sig_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno,
       source_kind, source_file, source_yyyymm, last_mvmn_de
  FROM latest
ON CONFLICT (bd_mgt_sn, pnu) DO UPDATE SET
  bjd_cd = EXCLUDED.bjd_cd,
  mntn_yn = EXCLUDED.mntn_yn,
  lnbr_mnnm = EXCLUDED.lnbr_mnnm,
  lnbr_slno = EXCLUDED.lnbr_slno,
  sig_cd = EXCLUDED.sig_cd,
  rn_cd = EXCLUDED.rn_cd,
  buld_se_cd = EXCLUDED.buld_se_cd,
  buld_mnnm = EXCLUDED.buld_mnnm,
  buld_slno = EXCLUDED.buld_slno,
  source_kind = EXCLUDED.source_kind,
  source_file = EXCLUDED.source_file,
  source_yyyymm = EXCLUDED.source_yyyymm,
  last_mvmn_de = EXCLUDED.last_mvmn_de,
  loaded_at = now()
""",
        params,
    )
    return _rowcount(cur.rowcount, fallback_rowcount)


async def _delete_latest_rows(
    cur: psycopg.AsyncCursor[Any],
    *,
    delete_codes: tuple[str, ...],
    fallback_rowcount: int,
) -> int:
    if not delete_codes:
        return 0
    await cur.execute(
        """
WITH latest AS (
  SELECT DISTINCT ON (bd_mgt_sn, pnu) bd_mgt_sn, pnu, mvm_res_cd
    FROM _juso_parcel_link_staging
   ORDER BY bd_mgt_sn, pnu, mvmn_de DESC NULLS LAST, source_file DESC, staging_seq DESC
)
DELETE FROM tl_juso_parcel_link AS t
 USING latest AS s
 WHERE t.bd_mgt_sn = s.bd_mgt_sn
   AND t.pnu = s.pnu
   AND s.mvm_res_cd = ANY(%s::text[])
""",
        (list(delete_codes),),
    )
    return _rowcount(cur.rowcount, fallback_rowcount)


async def _upsert_manifest(
    cur: psycopg.AsyncCursor[Any],
    *,
    source_path: Path,
    source_kind: str,
    processed_rows: int,
    source_count: int,
    skipped_no_data_sources: int,
    upsert_candidates: int,
    delete_candidates: int,
    upserted_rows: int,
    deleted_rows: int,
    last_mvmn_de: str | None,
    source_yyyymm: str | None,
    full_load: bool,
) -> None:
    source_set = {
        "kind": source_kind,
        "source_count": source_count,
        "processed_rows": processed_rows,
        "upsert_candidates": upsert_candidates,
        "delete_candidates": delete_candidates,
        "upserted_rows": upserted_rows,
        "deleted_rows": deleted_rows,
        "skipped_no_data_sources": skipped_no_data_sources,
    }
    full_column = "last_full_load_at"
    delta_column = "last_delta_at"
    values = {
        "last_full_load_at": "now()" if full_load else "NULL",
        "last_delta_at": "NULL" if full_load else "now()",
    }
    await cur.execute(
        f"""
INSERT INTO load_manifest (
  table_name, {full_column}, {delta_column}, last_mvmn_de, row_count, source_zip,
  source_checksum, source_yyyymm, source_set, updated_at
) VALUES (
  'tl_juso_parcel_link', {values["last_full_load_at"]}, {values["last_delta_at"]},
  %s, %s, %s, %s, %s, %s::jsonb, now()
)
ON CONFLICT (table_name) DO UPDATE SET
  {full_column} = COALESCE(EXCLUDED.{full_column}, load_manifest.{full_column}),
  {delta_column} = COALESCE(EXCLUDED.{delta_column}, load_manifest.{delta_column}),
  last_mvmn_de = EXCLUDED.last_mvmn_de,
  row_count = EXCLUDED.row_count,
  source_zip = EXCLUDED.source_zip,
  source_checksum = EXCLUDED.source_checksum,
  source_yyyymm = EXCLUDED.source_yyyymm,
  source_set = EXCLUDED.source_set,
  updated_at = now()
""",
        (
            last_mvmn_de,
            processed_rows,
            str(source_path),
            _source_checksum(source_path, source_kind=source_kind),
            source_yyyymm,
            json.dumps(source_set, ensure_ascii=False, sort_keys=True),
        ),
    )


def _source_checksum(source_path: Path, *, source_kind: str) -> str:
    if source_path.is_file():
        return sha256_file(source_path)
    if source_path.is_dir():
        digest = hashlib.sha256()
        patterns = (
            (JIBUN_RNADDRKOR_PATTERN,)
            if source_kind == "jibun_full"
            else ("*.zip", DAILY_LNBR_PATTERN)
        )
        candidates = {
            source
            for pattern in patterns
            for source in source_path.glob(pattern)
            if source.is_file()
        }
        for source in sorted(candidates):
            digest.update(source.name.encode())
            digest.update(b"\0")
            digest.update(sha256_file(source).encode())
            digest.update(b"\0")
        return digest.hexdigest()
    msg = f"parcel link source path does not exist: {source_path}"
    raise LoaderError(msg)


def _rowcount(rowcount: int, fallback: int) -> int:
    return rowcount if rowcount >= 0 else fallback


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
