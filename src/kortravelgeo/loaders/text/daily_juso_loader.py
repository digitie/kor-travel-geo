"""Loader for 도로명주소 일변동 ZIP files."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.manifest import infer_yyyymm, sha256_file
from kortravelgeo.settings import LoadCodeAction, get_settings

from .common import TextSource, discover_text_sources, iter_pipe_rows, required
from .juso_hangul_loader import JusoTextRow, juso_text_copy_tuple, parse_juso_row

ProgressCallback = Callable[[float], None]

DAILY_MST_PATTERN = "AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT"
DAILY_LNBR_PATTERN = "AlterD.JUSUKR.*.TH_SGCO_RNADR_LNBR.TXT"


@dataclass(frozen=True, slots=True)
class DailyJusoSourceSet:
    mst: tuple[TextSource, ...]
    lnbr: tuple[TextSource, ...]


@dataclass(frozen=True, slots=True)
class DailyJusoRow:
    juso: JusoTextRow
    mvm_res_cd: str
    mvmn_de: str | None
    line_no: int


@dataclass(frozen=True, slots=True)
class DailyJusoLoadResult:
    source_count: int
    processed_rows: int
    upsert_candidates: int
    delete_candidates: int
    upserted_rows: int
    deleted_rows: int
    unsupported_lnbr_rows: int
    skipped_no_data_sources: int
    last_mvmn_de: str | None
    source_yyyymm: str | None


def discover_daily_juso_sources(path: Path | str) -> DailyJusoSourceSet:
    root = Path(path)
    if not root.exists():
        msg = f"daily juso source path does not exist: {root}"
        raise LoaderError(msg)
    mst_sources = _discover_daily_text_sources(root, DAILY_MST_PATTERN)
    lnbr_sources = _discover_daily_text_sources(root, DAILY_LNBR_PATTERN)
    if not mst_sources and not lnbr_sources:
        msg = f"daily juso source contains no MST/LNBR members: {root}"
        raise LoaderError(msg)
    return DailyJusoSourceSet(mst=mst_sources, lnbr=lnbr_sources)


def iter_daily_juso_rows(
    source: TextSource,
    *,
    source_yyyymm: str | None,
    limit: int | None = None,
) -> Iterator[DailyJusoRow]:
    if is_no_data_source(source):
        return
    mvmn_de = infer_daily_mvmn_de(source)
    effective_yyyymm = source_yyyymm or (mvmn_de[:6] if mvmn_de else None)
    for index, (line_no, row) in enumerate(iter_pipe_rows(source, min_columns=24)):
        if limit is not None and index >= limit:
            return
        mvm_res_cd = required(
            row[20],
            field="mvm_res_cd",
            source_name=source.name,
            line_no=line_no,
        )
        yield DailyJusoRow(
            juso=parse_juso_row(
                row,
                source_name=source.name,
                line_no=line_no,
                source_yyyymm=effective_yyyymm,
            ),
            mvm_res_cd=mvm_res_cd,
            mvmn_de=mvmn_de,
            line_no=line_no,
        )


async def load_daily_juso_delta(
    engine: AsyncEngine,
    path: Path | str,
    *,
    source_yyyymm: str | None = None,
    code_actions: Mapping[str, LoadCodeAction] | None = None,
    limit_per_file: int | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> DailyJusoLoadResult:
    sources = discover_daily_juso_sources(path)
    actions = dict(code_actions or get_settings().mvm_res_code_actions)
    upsert_codes, delete_codes = _action_codes(actions)
    no_data_count = sum(1 for source in (*sources.mst, *sources.lnbr) if is_no_data_source(source))
    unsupported_lnbr_rows = sum(_count_lnbr_rows(source) for source in sources.lnbr)
    rows = _iter_many(
        sources.mst,
        source_yyyymm=source_yyyymm,
        limit_per_file=limit_per_file,
    )
    result = await copy_daily_juso_delta_rows(
        engine,
        rows,
        source_path=Path(path),
        source_count=len(sources.mst) + len(sources.lnbr),
        skipped_no_data_sources=no_data_count,
        unsupported_lnbr_rows=unsupported_lnbr_rows,
        last_mvmn_de=_max_mvmn_de((*sources.mst, *sources.lnbr)),
        manifest_source_yyyymm=source_yyyymm,
        code_actions=actions,
        upsert_codes=upsert_codes,
        delete_codes=delete_codes,
        on_progress=on_progress,
        cancel_event=cancel_event,
    )
    if on_progress:
        on_progress(1.0)
    return result


async def copy_daily_juso_delta_rows(
    engine: AsyncEngine,
    rows: Iterable[DailyJusoRow],
    *,
    source_path: Path,
    source_count: int,
    skipped_no_data_sources: int,
    unsupported_lnbr_rows: int,
    last_mvmn_de: str | None,
    manifest_source_yyyymm: str | None,
    code_actions: Mapping[str, LoadCodeAction],
    upsert_codes: tuple[str, ...],
    delete_codes: tuple[str, ...],
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> DailyJusoLoadResult:
    processed_rows = 0
    upsert_candidates = 0
    delete_candidates = 0
    async with await psycopg.AsyncConnection.connect(_alchemy_to_libpq(engine)) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
CREATE TEMP TABLE _juso_daily_staging (
  LIKE tl_juso_text INCLUDING DEFAULTS EXCLUDING GENERATED
) ON COMMIT DROP
"""
            )
            await cur.execute("ALTER TABLE _juso_daily_staging ADD COLUMN mvm_res_cd TEXT NOT NULL")
            await cur.execute("ALTER TABLE _juso_daily_staging ADD COLUMN mvmn_de TEXT")
            await cur.execute("ALTER TABLE _juso_daily_staging ADD COLUMN staging_seq BIGSERIAL")
            async with cur.copy(
                """
COPY _juso_daily_staging
(bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
 bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
 mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm, mvm_res_cd, mvmn_de)
FROM STDIN
"""
            ) as copy:
                for row in rows:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("daily_juso_loader cancelled")
                    action = code_actions.get(row.mvm_res_cd)
                    if action is None:
                        msg = (
                            f"{row.juso.source_file}:{row.line_no} unsupported "
                            f"mvm_res_cd={row.mvm_res_cd}"
                        )
                        raise LoaderError(msg)
                    await copy.write_row(
                        (*juso_text_copy_tuple(row.juso), row.mvm_res_cd, row.mvmn_de)
                    )
                    processed_rows += 1
                    if action in {"insert", "update"}:
                        upsert_candidates += 1
                    elif action == "delete":
                        delete_candidates += 1
                    if on_progress and processed_rows % 10_000 == 0:
                        on_progress(0.0)
            upserted_rows = await _upsert_latest_rows(cur, upsert_codes, upsert_candidates)
            deleted_rows = await _delete_latest_rows(cur, delete_codes, delete_candidates)
            effective_yyyymm = manifest_source_yyyymm or (
                last_mvmn_de[:6] if last_mvmn_de else infer_yyyymm(source_path)
            )
            await _upsert_manifest(
                cur,
                source_path=source_path,
                processed_rows=processed_rows,
                source_count=source_count,
                skipped_no_data_sources=skipped_no_data_sources,
                unsupported_lnbr_rows=unsupported_lnbr_rows,
                upsert_candidates=upsert_candidates,
                delete_candidates=delete_candidates,
                upserted_rows=upserted_rows,
                deleted_rows=deleted_rows,
                last_mvmn_de=last_mvmn_de,
                source_yyyymm=effective_yyyymm,
            )
        await conn.commit()
    return DailyJusoLoadResult(
        source_count=source_count,
        processed_rows=processed_rows,
        upsert_candidates=upsert_candidates,
        delete_candidates=delete_candidates,
        upserted_rows=upserted_rows,
        deleted_rows=deleted_rows,
        unsupported_lnbr_rows=unsupported_lnbr_rows,
        skipped_no_data_sources=skipped_no_data_sources,
        last_mvmn_de=last_mvmn_de,
        source_yyyymm=manifest_source_yyyymm
        or (last_mvmn_de[:6] if last_mvmn_de else infer_yyyymm(source_path)),
    )


def is_no_data_source(source: TextSource) -> bool:
    if source.size > 64:
        return False
    with source.open_binary() as file:
        sample = file.read(64)
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return sample.decode(encoding).strip() == "No Data"
        except UnicodeDecodeError:
            continue
    return False


def infer_daily_mvmn_de(source: TextSource) -> str | None:
    for value in (source.name, source.path.name):
        match = re.search(r"JUSUKR\.(20\d{6})\.", value)
        if match:
            return match.group(1)
        fallback = re.search(r"(20\d{6})", value)
        if fallback:
            return fallback.group(1)
    return None


def _discover_daily_text_sources(root: Path, pattern: str) -> tuple[TextSource, ...]:
    if root.is_dir():
        sources: list[TextSource] = list(discover_text_sources(root, pattern=pattern))
        for archive in sorted(root.glob("*.zip")):
            if archive.is_file():
                sources.extend(discover_text_sources(archive, pattern=pattern))
        return tuple(sorted(sources, key=lambda source: (source.path.name, source.name)))
    return discover_text_sources(root, pattern=pattern)


def _iter_many(
    sources: Iterable[TextSource],
    *,
    source_yyyymm: str | None,
    limit_per_file: int | None,
) -> Iterator[DailyJusoRow]:
    for source in sources:
        yield from iter_daily_juso_rows(
            source,
            source_yyyymm=source_yyyymm,
            limit=limit_per_file,
        )


def _count_lnbr_rows(source: TextSource) -> int:
    if is_no_data_source(source):
        return 0
    return sum(1 for _line_no, _row in iter_pipe_rows(source, min_columns=14))


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


async def _upsert_latest_rows(
    cur: psycopg.AsyncCursor[Any],
    upsert_codes: tuple[str, ...],
    fallback_rowcount: int,
) -> int:
    if not upsert_codes:
        return 0
    await cur.execute(
        """
WITH latest AS (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
         bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
         mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm, mvm_res_cd
    FROM _juso_daily_staging
   ORDER BY bd_mgt_sn, mvmn_de DESC NULLS LAST, source_file DESC, staging_seq DESC
)
INSERT INTO tl_juso_text AS t (
  bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
  bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
  mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm
)
SELECT bd_mgt_sn, sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
       bjd_cd, adm_cd, adm_kor_nm, rn, buld_se_cd, buld_mnnm, buld_slno, buld_nm,
       mntn_yn, lnbr_mnnm, lnbr_slno, zip_no, source_file, source_yyyymm
  FROM latest
 WHERE mvm_res_cd = ANY(%s::text[])
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
""",
        (list(upsert_codes),),
    )
    return _rowcount(cur.rowcount, fallback_rowcount)


async def _delete_latest_rows(
    cur: psycopg.AsyncCursor[Any],
    delete_codes: tuple[str, ...],
    fallback_rowcount: int,
) -> int:
    if not delete_codes:
        return 0
    await cur.execute(
        """
WITH latest AS (
  SELECT DISTINCT ON (bd_mgt_sn) bd_mgt_sn, mvm_res_cd
    FROM _juso_daily_staging
   ORDER BY bd_mgt_sn, mvmn_de DESC NULLS LAST, source_file DESC, staging_seq DESC
)
DELETE FROM tl_juso_text AS t
 USING latest AS s
 WHERE t.bd_mgt_sn = s.bd_mgt_sn
   AND s.mvm_res_cd = ANY(%s::text[])
""",
        (list(delete_codes),),
    )
    return _rowcount(cur.rowcount, fallback_rowcount)


async def _upsert_manifest(
    cur: psycopg.AsyncCursor[Any],
    *,
    source_path: Path,
    processed_rows: int,
    source_count: int,
    skipped_no_data_sources: int,
    unsupported_lnbr_rows: int,
    upsert_candidates: int,
    delete_candidates: int,
    upserted_rows: int,
    deleted_rows: int,
    last_mvmn_de: str | None,
    source_yyyymm: str | None,
) -> None:
    source_set = {
        "kind": "daily_juso_delta",
        "source_count": source_count,
        "processed_rows": processed_rows,
        "upsert_candidates": upsert_candidates,
        "delete_candidates": delete_candidates,
        "upserted_rows": upserted_rows,
        "deleted_rows": deleted_rows,
        "unsupported_lnbr_rows": unsupported_lnbr_rows,
        "skipped_no_data_sources": skipped_no_data_sources,
    }
    await cur.execute(
        """
INSERT INTO load_manifest (
  table_name, last_delta_at, last_mvmn_de, row_count, source_zip,
  source_checksum, source_yyyymm, source_set, updated_at
) VALUES (
  'tl_juso_text', now(), %s, %s, %s, %s, %s, %s::jsonb, now()
)
ON CONFLICT (table_name) DO UPDATE SET
  last_delta_at = EXCLUDED.last_delta_at,
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
            _source_checksum(source_path),
            source_yyyymm,
            json.dumps(source_set, ensure_ascii=False, sort_keys=True),
        ),
    )


def _source_checksum(source_path: Path) -> str:
    if source_path.is_file():
        return sha256_file(source_path)
    if source_path.is_dir():
        digest = hashlib.sha256()
        candidates = {
            *source_path.glob("*.zip"),
            *source_path.glob(DAILY_MST_PATTERN),
            *source_path.glob(DAILY_LNBR_PATTERN),
        }
        for source in sorted(candidate for candidate in candidates if candidate.is_file()):
            digest.update(source.name.encode())
            digest.update(b"\0")
            digest.update(sha256_file(source).encode())
            digest.update(b"\0")
        return digest.hexdigest()
    msg = f"daily juso source path does not exist: {source_path}"
    raise LoaderError(msg)


def _rowcount(rowcount: int, fallback: int) -> int:
    return rowcount if rowcount >= 0 else fallback


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
