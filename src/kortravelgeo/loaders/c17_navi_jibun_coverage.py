"""C17 navi ``match_jibun_*`` member coverage validation prototype."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import InvalidInputError, LoaderError
from kortravelgeo.infra.pnu import build_pnu
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    JoinKey,
    KeyOverlapMeasurement,
    measure_key_overlap,
)
from kortravelgeo.loaders.text.common import (
    TextSource,
    as_int,
    discover_text_sources,
    iter_pipe_rows,
    required,
)

C17_NAVI_JIBUN_SOURCE_KEY = "navi_full.match_jibun"
C17_NAVI_JIBUN_TABLE = "_ktg_c17_navi_jibun"
C17_NAVI_JIBUN_PATTERN = "match_jibun_*.txt"

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class NaviJibunMembers:
    match_jibun: tuple[TextSource, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "match_jibun_members": len(self.match_jibun),
            "match_jibun_present": int(bool(self.match_jibun)),
        }


@dataclass(frozen=True, slots=True)
class NaviJibunRow:
    source_file: str
    line_no: int
    bjd_cd: str
    pnu: str
    rncode_full: str
    sig_cd: str
    rn_cd: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    bd_mgt_sn: str
    adm_cd: str | None
    source_yyyymm: str | None

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.bjd_cd,
            self.pnu,
            self.rncode_full,
            self.sig_cd,
            self.rn_cd,
            self.buld_se_cd,
            self.buld_mnnm,
            self.buld_slno,
            self.bd_mgt_sn,
            self.adm_cd,
            self.source_yyyymm,
        )


@dataclass(frozen=True, slots=True)
class C17NaviJibunCoverageComparison:
    name: str
    left_source: str
    right_source: str
    key_contract: str
    join_keys: tuple[JoinKey, ...]
    overlap: KeyOverlapMeasurement
    sample: tuple[Mapping[str, object], ...]

    def metrics(self) -> dict[str, object]:
        return {
            "left_source": self.left_source,
            "right_source": self.right_source,
            "key_contract": self.key_contract,
            "join_keys": tuple((key.left, key.right) for key in self.join_keys),
            "key_overlap": _table_key_overlap_metrics(self.overlap),
        }


@dataclass(frozen=True, slots=True)
class C17NaviJibunCoverageResult:
    navi_path: str
    source_yyyymm: str | None
    members: NaviJibunMembers
    staging_rows: int
    comparisons: tuple[C17NaviJibunCoverageComparison, ...]
    limit_per_member: int | None = None

    def metrics(self) -> dict[str, object]:
        return {
            "navi_path": self.navi_path,
            "source_yyyymm": self.source_yyyymm,
            "source_category": "navi_full",
            "member_key": C17_NAVI_JIBUN_SOURCE_KEY,
            "source_members": self.members.counts,
            "staging_rows": {"navi_match_jibun": self.staging_rows},
            "limit_per_member": self.limit_per_member,
            "comparisons": {
                comparison.name: comparison.metrics() for comparison in self.comparisons
            },
            "notes": (
                "navi_full.match_jibun is an optional validation member inside "
                "navi_full, not an independent source category. C17 stages only "
                "road/parcel keys from match_jibun_* and compares them with "
                "tl_juso_parcel_link; it does not load coordinates or promote "
                "navi parcel members into serving candidates."
            ),
            "coordinate_load": False,
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        for comparison in self.comparisons:
            for row in comparison.sample:
                rows.append({"comparison": comparison.name, **row})
        return tuple(rows)

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def discover_navi_jibun_members(path: Path | str) -> NaviJibunMembers:
    return NaviJibunMembers(
        match_jibun=discover_text_sources(path, pattern=C17_NAVI_JIBUN_PATTERN)
    )


def parse_navi_jibun_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
    source_yyyymm: str | None,
) -> NaviJibunRow:
    bjd_cd = required(row[0], field="bjd_cd", source_name=source_name, line_no=line_no)
    mntn_yn = required(row[5], field="mntn_yn", source_name=source_name, line_no=line_no)
    lnbr_mnnm = _required_int(row[6], field="lnbr_mnnm", source_name=source_name, line_no=line_no)
    lnbr_slno = as_int(row[7]) or 0
    rncode_full = _required_rncode_full(row[8], source_name=source_name, line_no=line_no)
    pnu = _build_pnu(
        bjd_cd=bjd_cd,
        mntn_yn=mntn_yn,
        lnbr_mnnm=lnbr_mnnm,
        lnbr_slno=lnbr_slno,
        source_name=source_name,
        line_no=line_no,
    )
    return NaviJibunRow(
        source_file=source_name,
        line_no=line_no,
        bjd_cd=bjd_cd,
        pnu=pnu,
        rncode_full=rncode_full,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        buld_se_cd=row[9] or None,
        buld_mnnm=as_int(row[10]),
        buld_slno=as_int(row[11]),
        bd_mgt_sn=required(row[18], field="bd_mgt_sn", source_name=source_name, line_no=line_no),
        adm_cd=row[19] or None,
        source_yyyymm=source_yyyymm,
    )


def iter_navi_jibun_rows(
    path: Path | str,
    *,
    source_yyyymm: str | None,
    limit_per_member: int | None = None,
) -> Iterator[NaviJibunRow]:
    members = discover_navi_jibun_members(path)
    for source in members.match_jibun:
        for index, (line_no, row) in enumerate(iter_pipe_rows(source, min_columns=20)):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_navi_jibun_row(
                row,
                source_name=source.name,
                line_no=line_no,
                source_yyyymm=source_yyyymm,
            )


async def compare_c17_navi_jibun_coverage(
    engine: AsyncEngine,
    navi_path: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    limit_per_member: int | None = None,
    staging_table: str = C17_NAVI_JIBUN_TABLE,
) -> C17NaviJibunCoverageResult:
    path = Path(navi_path)
    members = discover_navi_jibun_members(path)
    if not members.match_jibun:
        msg = f"{C17_NAVI_JIBUN_SOURCE_KEY} has no {C17_NAVI_JIBUN_PATTERN} members: {path}"
        raise LoaderError(msg)

    await recreate_c17_navi_jibun_staging_table(engine, staging_table=staging_table)
    staging_rows = await copy_navi_jibun_rows_to_staging(
        engine,
        (
            row.copy_tuple()
            for row in iter_navi_jibun_rows(
                path,
                source_yyyymm=source_yyyymm,
                limit_per_member=limit_per_member,
            )
        ),
        staging_table=staging_table,
    )
    comparisons = (
        await _measure_comparison(
            engine,
            name="navi_jibun_to_tl_juso_parcel_link_bd_pnu",
            left_source="navi_full.match_jibun_*.txt",
            left_table=staging_table,
            right_source="tl_juso_parcel_link",
            right_table="tl_juso_parcel_link",
            key_contract="bd_mgt_sn_pnu",
            join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"), JoinKey("pnu", "pnu")),
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="navi_jibun_to_tl_juso_parcel_link_pnu_road_key",
            left_source="navi_full.match_jibun_*.txt",
            left_table=staging_table,
            right_source="tl_juso_parcel_link",
            right_table="tl_juso_parcel_link",
            key_contract="pnu_rncode_buld",
            join_keys=(
                JoinKey("pnu", "pnu"),
                JoinKey("rncode_full", "rncode_full"),
                JoinKey("buld_se_cd", "buld_se_cd"),
                JoinKey("buld_mnnm", "buld_mnnm"),
                JoinKey("buld_slno", "buld_slno"),
            ),
            sample_limit=sample_limit,
        ),
    )
    return C17NaviJibunCoverageResult(
        navi_path=str(path),
        source_yyyymm=source_yyyymm,
        members=members,
        staging_rows=staging_rows,
        comparisons=comparisons,
        limit_per_member=limit_per_member,
    )


async def build_c17_navi_jibun_coverage_report(
    engine: AsyncEngine,
    navi_path: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    limit_per_member: int | None = None,
    generated_at: datetime | None = None,
) -> AugmentReport:
    path = Path(navi_path)
    try:
        members = discover_navi_jibun_members(path)
        if not members.match_jibun:
            result = _skipped_result(path, source_yyyymm=source_yyyymm, members=members)
        else:
            comparison = await compare_c17_navi_jibun_coverage(
                engine,
                path,
                source_yyyymm=source_yyyymm,
                sample_limit=sample_limit,
                limit_per_member=limit_per_member,
            )
            payload = comparison.to_payload()
            result = AugmentGroupResult(
                group_id="national",
                sido_name="전국",
                status="used",
                metrics=payload.metrics,
                sample=payload.sample,
                source_yyyymm=payload.source_yyyymm,
            )
    except Exception as exc:
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="failed",
            metrics={},
            error=f"{type(exc).__name__}: {exc}",
            source_yyyymm=source_yyyymm,
        )
    return AugmentReport(
        task_id="T-117",
        title="C17 navi match_jibun member coverage validation",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=(result,),
        source_yyyymm=source_yyyymm,
    )


async def recreate_c17_navi_jibun_staging_table(
    engine: AsyncEngine,
    *,
    staging_table: str = C17_NAVI_JIBUN_TABLE,
) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(staging_table)}"))
        await conn.execute(text(c17_navi_jibun_staging_create_sql(staging_table)))


def c17_navi_jibun_staging_create_sql(table_name: str = C17_NAVI_JIBUN_TABLE) -> str:
    return f"""
CREATE TABLE {_quote_ident_path(table_name)} (
  source_file text NOT NULL,
  line_no bigint NOT NULL,
  bjd_cd text NOT NULL,
  pnu text NOT NULL,
  rncode_full text NOT NULL,
  sig_cd text NOT NULL,
  rn_cd text NOT NULL,
  buld_se_cd text,
  buld_mnnm integer,
  buld_slno integer,
  bd_mgt_sn text NOT NULL,
  adm_cd text,
  source_yyyymm text
)
"""


async def copy_navi_jibun_rows_to_staging(
    engine: AsyncEngine,
    rows: Iterable[Sequence[object]],
    *,
    staging_table: str = C17_NAVI_JIBUN_TABLE,
) -> int:
    copied = 0
    async with await psycopg.AsyncConnection.connect(
        _alchemy_to_libpq(engine),
        autocommit=False,
    ) as conn, conn.cursor() as cur:
        async with cur.copy(c17_navi_jibun_copy_sql(staging_table)) as copy:
            for row in rows:
                await copy.write_row(row)
                copied += 1
        await conn.commit()
    return copied


def c17_navi_jibun_copy_sql(table_name: str = C17_NAVI_JIBUN_TABLE) -> str:
    return f"""
COPY {_quote_ident_path(table_name)}
(source_file, line_no, bjd_cd, pnu, rncode_full, sig_cd, rn_cd, buld_se_cd,
 buld_mnnm, buld_slno, bd_mgt_sn, adm_cd, source_yyyymm)
FROM STDIN
"""


async def measure_key_coverage(
    engine: AsyncEngine,
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    sample_limit: int = 20,
) -> tuple[KeyOverlapMeasurement, tuple[Mapping[str, object], ...]]:
    overlap = await measure_key_overlap(engine, left_table, right_table, key_pairs)
    sql = key_coverage_sample_sql(left_table, right_table, key_pairs)
    async with engine.connect() as conn:
        sample_value = await conn.scalar(text(sql), {"sample_limit": sample_limit})
    return overlap, _jsonb_sample(sample_value)


def key_coverage_sample_sql(
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
) -> str:
    if not key_pairs:
        msg = "at least one join key is required"
        raise LoaderError(msg)
    left_select = _key_alias_columns("l", tuple(pair.left for pair in key_pairs))
    right_select = _key_alias_columns_as(
        "r",
        tuple((pair.right, pair.left) for pair in key_pairs),
    )
    left_where = _nonnull_key_condition("l", tuple(pair.left for pair in key_pairs))
    right_where = _nonnull_key_condition("r", tuple(pair.right for pair in key_pairs))
    order_columns = ", ".join(_quote_ident(pair.left) for pair in key_pairs)
    return f"""
WITH left_keys AS (
  SELECT DISTINCT {left_select}
    FROM {_quote_ident_path(left_table)} l
   WHERE {left_where}
),
right_keys AS (
  SELECT DISTINCT {right_select}
    FROM {_quote_ident_path(right_table)} r
   WHERE {right_where}
),
left_only AS (
  SELECT * FROM left_keys
  EXCEPT
  SELECT * FROM right_keys
),
right_only AS (
  SELECT * FROM right_keys
  EXCEPT
  SELECT * FROM left_keys
),
sample AS (
  (
    SELECT 'left_only'::text AS sample_kind, to_jsonb(left_only) AS keys
      FROM left_only
     ORDER BY {order_columns}
     LIMIT :sample_limit
  )
  UNION ALL
  (
    SELECT 'right_only'::text AS sample_kind, to_jsonb(right_only) AS keys
      FROM right_only
     ORDER BY {order_columns}
     LIMIT :sample_limit
  )
)
SELECT COALESCE(jsonb_agg(to_jsonb(sample)), '[]'::jsonb) AS sample
  FROM sample
"""


async def drop_c17_navi_jibun_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (C17_NAVI_JIBUN_TABLE,),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table)}"))


async def _measure_comparison(
    engine: AsyncEngine,
    *,
    name: str,
    left_source: str,
    left_table: str,
    right_source: str,
    right_table: str,
    key_contract: str,
    join_keys: tuple[JoinKey, ...],
    sample_limit: int,
) -> C17NaviJibunCoverageComparison:
    overlap, sample = await measure_key_coverage(
        engine,
        left_table,
        right_table,
        join_keys,
        sample_limit=sample_limit,
    )
    return C17NaviJibunCoverageComparison(
        name=name,
        left_source=left_source,
        right_source=right_source,
        key_contract=key_contract,
        join_keys=join_keys,
        overlap=overlap,
        sample=sample,
    )


def _skipped_result(
    navi_path: Path,
    *,
    source_yyyymm: str | None,
    members: NaviJibunMembers,
) -> AugmentGroupResult:
    return AugmentGroupResult(
        group_id="national",
        sido_name="전국",
        status="skipped",
        metrics={
            "navi_path": str(navi_path),
            "source_yyyymm": source_yyyymm,
            "source_category": "navi_full",
            "member_key": C17_NAVI_JIBUN_SOURCE_KEY,
            "source_members": members.counts,
            "skip_reason": f"{C17_NAVI_JIBUN_PATTERN} member 없음",
            "coordinate_load": False,
            "serving_promotion": False,
        },
        source_yyyymm=source_yyyymm,
    )


def _required_int(
    value: str | None,
    *,
    field: str,
    source_name: str,
    line_no: int,
) -> int:
    parsed = as_int(value)
    if parsed is None:
        msg = f"{source_name}:{line_no} missing required integer field {field}"
        raise LoaderError(msg)
    return parsed


def _required_rncode_full(value: str | None, *, source_name: str, line_no: int) -> str:
    rncode_full = required(value, field="rncode_full", source_name=source_name, line_no=line_no)
    if len(rncode_full) != 12 or not rncode_full.isdigit():
        msg = f"{source_name}:{line_no} rncode_full must be a 12-digit string"
        raise LoaderError(msg)
    return rncode_full


def _build_pnu(
    *,
    bjd_cd: str,
    mntn_yn: str,
    lnbr_mnnm: int,
    lnbr_slno: int,
    source_name: str,
    line_no: int,
) -> str:
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
        msg = f"{source_name}:{line_no} row cannot build PNU"
        raise LoaderError(msg)
    return pnu


def _table_key_overlap_metrics(value: KeyOverlapMeasurement) -> dict[str, int]:
    return {
        "left_rows": value.left_rows,
        "right_rows": value.right_rows,
        "left_distinct": value.left_distinct,
        "right_distinct": value.right_distinct,
        "left_duplicate_count": value.left_duplicate_count,
        "right_duplicate_count": value.right_duplicate_count,
        "intersection_count": value.intersection_count,
        "left_only_count": value.left_only_count,
        "right_only_count": value.right_only_count,
    }


def _jsonb_sample(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    rows: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return tuple(rows)


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _key_alias_columns(alias: str, columns: Sequence[str]) -> str:
    return ", ".join(
        f"{alias}.{_quote_ident(column)}::text AS {_quote_ident(column)}"
        for column in columns
    )


def _key_alias_columns_as(alias: str, columns: Sequence[tuple[str, str]]) -> str:
    return ", ".join(
        f"{alias}.{_quote_ident(source)}::text AS {_quote_ident(target)}"
        for source, target in columns
    )


def _nonnull_key_condition(alias: str, columns: Sequence[str]) -> str:
    return " AND ".join(f"{alias}.{_quote_ident(column)} IS NOT NULL" for column in columns)


def _quote_ident_path(value: str) -> str:
    return ".".join(_quote_ident(part) for part in value.split("."))


def _quote_ident(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid SQL identifier: {value!r}"
        raise LoaderError(msg)
    return f'"{value}"'
