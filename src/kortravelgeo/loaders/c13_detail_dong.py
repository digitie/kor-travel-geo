"""C13 detail-address dong containment validation prototype."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import SupportsFloat

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    CoversMeasurement,
    JoinKey,
    KeyOverlapMeasurement,
    ShapeStagingSpec,
    SidoPathPattern,
    SidoSourceGroup,
    SidoSourcePath,
    StagingColumn,
    copy_zip_shape_layer_to_staging,
    discover_sido_source_groups,
    measure_key_overlap,
    measure_keyed_covers,
    recreate_shape_staging_table,
)
from kortravelgeo.loaders.extra_shape_layers import (
    DETAIL_DONG_ENTRANCE_LAYER,
    DETAIL_DONG_POLYGON_LAYER,
)

C13_DETAIL_DONG_SOURCE_KEY = "detail_dong"
C13_DETAIL_ADDRESS_SOURCE_KEY = "detail_address_db"

C13_DETAIL_DONG_POLYGON_TABLE = "_ktg_c13_detail_dong_polygon"
C13_DETAIL_DONG_ENTRANCE_TABLE = "_ktg_c13_detail_dong_entrc"
C13_DETAIL_ADDRESS_TABLE = "_ktg_c13_detail_address"

DETAIL_DONG_POLYGON_SOURCE_FIELDS: tuple[str, ...] = (
    "ADR_MNG_NO",
    "BD_MGT_SN",
    "SIG_CD",
    "BUL_MAN_NO",
    "RN_CD",
    "BULD_SE_CD",
    "BULD_MNNM",
    "BULD_SLNO",
    "EQB_MAN_SN",
)
DETAIL_DONG_ENTRANCE_SOURCE_FIELDS: tuple[str, ...] = (
    "SIG_CD",
    "ENT_MAN_NO",
    "BUL_MAN_NO",
    "ENTRC_SE",
    "OPERT_DE",
    "ENTRC_DC",
)

DETAIL_ADDRESS_MEMBER_BY_SIDO: Mapping[str, str] = {
    "서울특별시": "adrdc_seoul.txt",
    "부산광역시": "adrdc_busan.txt",
    "대구광역시": "adrdc_daegu.txt",
    "인천광역시": "adrdc_incheon.txt",
    "광주광역시": "adrdc_gwangju.txt",
    "대전광역시": "adrdc_daejeon.txt",
    "울산광역시": "adrdc_ulsan.txt",
    "세종특별자치시": "adrdc_sejong.txt",
    "경기도": "adrdc_gyunggi.txt",
    "강원특별자치도": "adrdc_gangwon.txt",
    "충청북도": "adrdc_chungbuk.txt",
    "충청남도": "adrdc_chungnam.txt",
    "전북특별자치도": "adrdc_jeonbuk.txt",
    "전라남도": "adrdc_jeonnam.txt",
    "경상북도": "adrdc_gyeongbuk.txt",
    "경상남도": "adrdc_gyeongnam.txt",
    "제주특별자치도": "adrdc_jeju.txt",
}

DETAIL_ADDRESS_COPY_COLUMNS: tuple[str, ...] = (
    "source_member",
    "line_number",
    "sig_cd",
    "dong_serial_no",
    "floor_serial_no",
    "unit_serial_no",
    "unit_suffix_serial_no",
    "dong_name",
    "floor_name",
    "unit_name",
    "unit_suffix_name",
    "underground_flag",
    "building_management_no",
    "legal_dong_cd",
    "road_name_cd",
    "road_name_no",
    "road_underground_yn",
    "building_main_no",
    "building_sub_no",
)

BUILDING_MANAGEMENT_JOIN_KEYS: tuple[JoinKey, ...] = (
    JoinKey("bd_mgt_sn", "building_management_no"),
)
ROAD_ADDRESS_JOIN_KEYS: tuple[JoinKey, ...] = (
    JoinKey("sig_cd", "sig_cd"),
    JoinKey("rn_cd", "road_name_no"),
    JoinKey("buld_se_cd", "road_underground_yn"),
    JoinKey("buld_mnnm", "building_main_no"),
    JoinKey("buld_slno", "building_sub_no"),
)
ENTRANCE_BUILDING_REF_JOIN_KEYS: tuple[JoinKey, ...] = (
    JoinKey("sig_cd", "sig_cd"),
    JoinKey("bul_man_no", "bul_man_no"),
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSIGNED_INT_RE = re.compile(r"^[0-9]+$")


@dataclass(frozen=True, slots=True)
class DetailAddressRow:
    source_member: str
    line_number: int
    sig_cd: str | None
    dong_serial_no: str | None
    floor_serial_no: str | None
    unit_serial_no: str | None
    unit_suffix_serial_no: str | None
    dong_name: str | None
    floor_name: str | None
    unit_name: str | None
    unit_suffix_name: str | None
    underground_flag: str | None
    building_management_no: str | None
    legal_dong_cd: str | None
    road_name_cd: str | None
    road_name_no: str | None
    road_underground_yn: str | None
    building_main_no: str | None
    building_sub_no: str | None

    @classmethod
    def from_columns(
        cls,
        columns: Sequence[str],
        *,
        source_member: str,
        line_number: int,
    ) -> DetailAddressRow:
        if len(columns) != 16:
            msg = f"{source_member}:{line_number} expected 16 columns, got {len(columns)}"
            raise LoaderError(msg)

        def int_field(index: int, field_name: str) -> str | None:
            return _normalize_int_text(
                columns[index],
                field_name=field_name,
                source_member=source_member,
                line_number=line_number,
            )

        road_name_cd = _blank_to_none(columns[12])
        return cls(
            source_member=source_member,
            line_number=line_number,
            sig_cd=_blank_to_none(columns[0]),
            dong_serial_no=int_field(1, "dong_serial_no"),
            floor_serial_no=int_field(2, "floor_serial_no"),
            unit_serial_no=int_field(3, "unit_serial_no"),
            unit_suffix_serial_no=int_field(4, "unit_suffix_serial_no"),
            dong_name=_blank_to_none(columns[5]),
            floor_name=_blank_to_none(columns[6]),
            unit_name=_blank_to_none(columns[7]),
            unit_suffix_name=_blank_to_none(columns[8]),
            underground_flag=_blank_to_none(columns[9]),
            building_management_no=_blank_to_none(columns[10]),
            legal_dong_cd=_blank_to_none(columns[11]),
            road_name_cd=road_name_cd,
            road_name_no=_road_name_no(road_name_cd),
            road_underground_yn=_blank_to_none(columns[13]),
            building_main_no=int_field(14, "building_main_no"),
            building_sub_no=int_field(15, "building_sub_no"),
        )

    def copy_row(self) -> tuple[object, ...]:
        return tuple(getattr(self, column) for column in DETAIL_ADDRESS_COPY_COLUMNS)


@dataclass(frozen=True, slots=True)
class DetailDongEntranceContainmentMeasurement:
    total_pairs: int
    detail_address_matched_pairs: int
    covered: int
    outside: int
    detail_address_matched_covered: int
    detail_address_matched_outside: int
    coverage_ratio: float | None
    detail_address_matched_coverage_ratio: float | None
    sample: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class C13DetailDongComparison:
    sido_name: str
    detail_dong_zip: str
    detail_address_db_zip: str
    detail_address_member: str
    source_yyyymm: str | None
    detail_dong_rows: int
    detail_entrance_rows: int
    detail_address_rows: int
    building_management_overlap: KeyOverlapMeasurement
    road_address_overlap: KeyOverlapMeasurement
    entrance_building_ref_overlap: KeyOverlapMeasurement
    entrance_containment: CoversMeasurement
    entrance_containment_with_address: DetailDongEntranceContainmentMeasurement

    def metrics(self) -> dict[str, object]:
        return {
            "sido_name": self.sido_name,
            "detail_dong_zip": self.detail_dong_zip,
            "detail_address_db_zip": self.detail_address_db_zip,
            "detail_address_member": self.detail_address_member,
            "source_yyyymm": self.source_yyyymm,
            "staging_rows": {
                "detail_dong_tl_sgco_rnadr_dong": self.detail_dong_rows,
                "detail_dong_tl_spbd_entrc_dong": self.detail_entrance_rows,
                "detail_address_db_adrdc": self.detail_address_rows,
            },
            "key_overlaps": {
                "building_management_no_to_bd_mgt_sn": _table_key_overlap_metrics(
                    self.building_management_overlap
                ),
                "road_address_key_to_shape_fields": _table_key_overlap_metrics(
                    self.road_address_overlap
                ),
                "detail_entrance_sig_bul_to_polygon_sig_bul": _table_key_overlap_metrics(
                    self.entrance_building_ref_overlap
                ),
            },
            "containment": {
                "detail_entrance_point_in_detail_dong_polygon": _covers_metrics(
                    self.entrance_containment
                ),
                "detail_address_matched_detail_entrance_point_in_polygon": (
                    _detail_containment_metrics(self.entrance_containment_with_address)
                ),
            },
            "notes": (
                "detail_address_db has no geometry; ST_Covers is measured between "
                "TL_SGCO_RNADR_DONG polygons and TL_SPBD_ENTRC_DONG points, with "
                "detail_address_db contributing key-overlap and address-matched coverage context."
            ),
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        for row in self.entrance_containment.sample:
            rows.append({"sample_kind": "entrance_outside_polygon", **row})
        for row in self.entrance_containment_with_address.sample:
            rows.append({"sample_kind": "address_matched_containment_check", **row})
        return tuple(rows)

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def detail_dong_polygon_staging_spec(table_name: str) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("adr_mng_no", source_field="ADR_MNG_NO"),
            StagingColumn("bd_mgt_sn", source_field="BD_MGT_SN"),
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("bul_man_no", sql_type="bigint", source_field="BUL_MAN_NO"),
            StagingColumn("rn_cd", source_field="RN_CD"),
            StagingColumn("buld_se_cd", source_field="BULD_SE_CD"),
            StagingColumn("buld_mnnm", sql_type="bigint", source_field="BULD_MNNM"),
            StagingColumn("buld_slno", sql_type="bigint", source_field="BULD_SLNO"),
            StagingColumn("eqb_man_sn", sql_type="bigint", source_field="EQB_MAN_SN"),
        ),
        geometry_type="Geometry",
    )


def detail_dong_entrance_staging_spec(table_name: str) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("ent_man_no", sql_type="bigint", source_field="ENT_MAN_NO"),
            StagingColumn("bul_man_no", sql_type="bigint", source_field="BUL_MAN_NO"),
            StagingColumn("entrc_se", source_field="ENTRC_SE"),
            StagingColumn("opert_de", source_field="OPERT_DE"),
            StagingColumn("entrc_dc", source_field="ENTRC_DC"),
        ),
        geometry_type="Point",
    )


def detail_address_member_for_sido(sido_name: str) -> str:
    try:
        return DETAIL_ADDRESS_MEMBER_BY_SIDO[sido_name]
    except KeyError as exc:
        msg = f"unsupported sido for detail address DB: {sido_name}"
        raise LoaderError(msg) from exc


def iter_detail_address_rows(
    detail_address_db_zip: Path | str,
    *,
    member_name: str | None = None,
    encoding: str = "cp949",
) -> Iterator[DetailAddressRow]:
    archive = Path(detail_address_db_zip)
    with zipfile.ZipFile(archive) as zip_file:
        members = _detail_address_members(zip_file, member_name)
        for member in members:
            with zip_file.open(member) as file:
                for line_number, raw_line in enumerate(file, start=1):
                    line = raw_line.decode(encoding).rstrip("\r\n")
                    if not line:
                        continue
                    yield DetailAddressRow.from_columns(
                        line.split("|"),
                        source_member=member,
                        line_number=line_number,
                    )


def discover_c13_detail_dong_source_groups(
    *,
    detail_dong_root: Path | str,
    detail_address_db_zip: Path | str,
    sido_names: Sequence[str] | None = None,
) -> tuple[SidoSourceGroup, ...]:
    if sido_names is None:
        groups = discover_sido_source_groups(
            (
                SidoPathPattern(
                    C13_DETAIL_DONG_SOURCE_KEY,
                    Path(detail_dong_root),
                    "*{sido}*.zip",
                ),
            )
        )
    else:
        groups = discover_sido_source_groups(
            (
                SidoPathPattern(
                    C13_DETAIL_DONG_SOURCE_KEY,
                    Path(detail_dong_root),
                    "*{sido}*.zip",
                ),
            ),
            sido_names=sido_names,
        )

    address_path = Path(detail_address_db_zip)
    address_members = _zip_members(address_path) if address_path.is_file() else frozenset()
    enriched: list[SidoSourceGroup] = []
    for group in groups:
        missing = list(group.missing_keys)
        sources = list(group.sources)
        try:
            member = detail_address_member_for_sido(group.sido_name)
        except LoaderError:
            missing.append(C13_DETAIL_ADDRESS_SOURCE_KEY)
        else:
            if not address_path.is_file() or member not in address_members:
                missing.append(C13_DETAIL_ADDRESS_SOURCE_KEY)
            else:
                sources.append(SidoSourcePath(C13_DETAIL_ADDRESS_SOURCE_KEY, address_path))
        enriched.append(
            SidoSourceGroup(
                sido_name=group.sido_name,
                sources=tuple(sources),
                missing_keys=tuple(missing),
            )
        )
    return tuple(enriched)


async def compare_c13_detail_dong_containment(
    engine: AsyncEngine,
    detail_dong_zip: Path | str,
    detail_address_db_zip: Path | str,
    *,
    sido_name: str,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    polygon_table: str = C13_DETAIL_DONG_POLYGON_TABLE,
    entrance_table: str = C13_DETAIL_DONG_ENTRANCE_TABLE,
    detail_address_table: str = C13_DETAIL_ADDRESS_TABLE,
) -> C13DetailDongComparison:
    detail_path = Path(detail_dong_zip)
    address_path = Path(detail_address_db_zip)
    member_name = detail_address_member_for_sido(sido_name)

    polygon_spec = detail_dong_polygon_staging_spec(polygon_table)
    entrance_spec = detail_dong_entrance_staging_spec(entrance_table)
    await recreate_shape_staging_table(engine, polygon_spec)
    await recreate_shape_staging_table(engine, entrance_spec)
    await recreate_detail_address_staging_table(engine, detail_address_table)

    detail_dong_rows = await copy_zip_shape_layer_to_staging(
        engine,
        polygon_spec,
        detail_path,
        DETAIL_DONG_POLYGON_LAYER,
        fields=DETAIL_DONG_POLYGON_SOURCE_FIELDS,
    )
    detail_entrance_rows = await copy_zip_shape_layer_to_staging(
        engine,
        entrance_spec,
        detail_path,
        DETAIL_DONG_ENTRANCE_LAYER,
        fields=DETAIL_DONG_ENTRANCE_SOURCE_FIELDS,
    )
    detail_address_rows = await copy_detail_address_rows_to_staging(
        engine,
        detail_address_table,
        iter_detail_address_rows(address_path, member_name=member_name),
    )

    building_management_overlap = await measure_key_overlap(
        engine,
        polygon_table,
        detail_address_table,
        BUILDING_MANAGEMENT_JOIN_KEYS,
    )
    road_address_overlap = await measure_key_overlap(
        engine,
        polygon_table,
        detail_address_table,
        ROAD_ADDRESS_JOIN_KEYS,
    )
    entrance_building_ref_overlap = await measure_key_overlap(
        engine,
        entrance_table,
        polygon_table,
        ENTRANCE_BUILDING_REF_JOIN_KEYS,
    )
    entrance_containment = await measure_keyed_covers(
        engine,
        polygon_table,
        entrance_table,
        ENTRANCE_BUILDING_REF_JOIN_KEYS,
        sample_limit=sample_limit,
    )
    entrance_containment_with_address = await measure_detail_entrance_containment(
        engine,
        polygon_table,
        entrance_table,
        detail_address_table,
        sample_limit=sample_limit,
    )

    return C13DetailDongComparison(
        sido_name=sido_name,
        detail_dong_zip=str(detail_path),
        detail_address_db_zip=str(address_path),
        detail_address_member=member_name,
        source_yyyymm=source_yyyymm,
        detail_dong_rows=detail_dong_rows,
        detail_entrance_rows=detail_entrance_rows,
        detail_address_rows=detail_address_rows,
        building_management_overlap=building_management_overlap,
        road_address_overlap=road_address_overlap,
        entrance_building_ref_overlap=entrance_building_ref_overlap,
        entrance_containment=entrance_containment,
        entrance_containment_with_address=entrance_containment_with_address,
    )


async def build_c13_detail_dong_report(
    engine: AsyncEngine,
    groups: Iterable[SidoSourceGroup],
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    generated_at: datetime | None = None,
) -> AugmentReport:
    results: list[AugmentGroupResult] = []
    for group in groups:
        if group.missing_keys:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="skipped",
                    metrics={},
                    error="missing required source(s): " + ", ".join(group.missing_keys),
                )
            )
            continue
        try:
            comparison = await compare_c13_detail_dong_containment(
                engine,
                group.path(C13_DETAIL_DONG_SOURCE_KEY),
                group.path(C13_DETAIL_ADDRESS_SOURCE_KEY),
                sido_name=group.sido_name,
                source_yyyymm=source_yyyymm,
                sample_limit=sample_limit,
            )
        except Exception as exc:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="failed",
                    metrics={},
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        payload = comparison.to_payload()
        results.append(
            AugmentGroupResult(
                group_id=group.sido_name,
                sido_name=group.sido_name,
                status="used",
                metrics=payload.metrics,
                sample=payload.sample,
                source_yyyymm=payload.source_yyyymm or source_yyyymm,
            )
        )
    return AugmentReport(
        task_id="T-113",
        title="C13 detail-address dong containment validation",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=tuple(results),
        source_yyyymm=source_yyyymm,
    )


async def recreate_detail_address_staging_table(
    engine: AsyncEngine,
    table_name: str = C13_DETAIL_ADDRESS_TABLE,
) -> None:
    columns = tuple(
        f"{_quote_ident(column)} {'bigint' if column == 'line_number' else 'text'}"
        for column in DETAIL_ADDRESS_COPY_COLUMNS
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table_name)}"))
        await conn.execute(
            text(f"CREATE TABLE {_quote_ident_path(table_name)} ({', '.join(columns)})")
        )


async def copy_detail_address_rows_to_staging(
    engine: AsyncEngine,
    table_name: str,
    rows: Iterable[DetailAddressRow],
) -> int:
    copied = 0
    async with await psycopg.AsyncConnection.connect(
        _alchemy_to_libpq(engine),
        autocommit=False,
    ) as conn, conn.cursor() as cur:
        async with cur.copy(_detail_address_copy_sql(table_name)) as copy:
            for row in rows:
                await copy.write_row(row.copy_row())
                copied += 1
        await conn.commit()
    return copied


async def measure_detail_entrance_containment(
    engine: AsyncEngine,
    polygon_table: str,
    entrance_table: str,
    detail_address_table: str,
    *,
    sample_limit: int = 20,
) -> DetailDongEntranceContainmentMeasurement:
    sql = detail_entrance_containment_sql(
        polygon_table,
        entrance_table,
        detail_address_table,
    )
    async with engine.connect() as conn:
        row = (
            await conn.execute(text(sql), {"sample_limit": sample_limit})
        ).mappings().one()
    return DetailDongEntranceContainmentMeasurement(
        total_pairs=int(row["total_pairs"] or 0),
        detail_address_matched_pairs=int(row["detail_address_matched_pairs"] or 0),
        covered=int(row["covered"] or 0),
        outside=int(row["outside"] or 0),
        detail_address_matched_covered=int(row["detail_address_matched_covered"] or 0),
        detail_address_matched_outside=int(row["detail_address_matched_outside"] or 0),
        coverage_ratio=_optional_float(row["coverage_ratio"]),
        detail_address_matched_coverage_ratio=_optional_float(
            row["detail_address_matched_coverage_ratio"]
        ),
        sample=_jsonb_sample(row["sample"]),
    )


def detail_entrance_containment_sql(
    polygon_table: str,
    entrance_table: str,
    detail_address_table: str,
) -> str:
    return f"""
WITH detail_address_buildings AS (
  SELECT DISTINCT building_management_no
    FROM {_quote_ident_path(detail_address_table)}
   WHERE building_management_no IS NOT NULL
),
joined AS (
  SELECT
    p.sig_cd::text AS polygon_sig_cd,
    p.bul_man_no::text AS polygon_bul_man_no,
    p.bd_mgt_sn::text AS polygon_bd_mgt_sn,
    e.ent_man_no::text AS entrance_ent_man_no,
    (a.building_management_no IS NOT NULL) AS detail_address_key_matched,
    ST_Covers(p.geom, e.geom) AS covered
  FROM {_quote_ident_path(polygon_table)} p
  JOIN {_quote_ident_path(entrance_table)} e
    ON p.sig_cd = e.sig_cd
   AND p.bul_man_no = e.bul_man_no
  LEFT JOIN detail_address_buildings a
    ON a.building_management_no = p.bd_mgt_sn
 WHERE p.geom IS NOT NULL
   AND e.geom IS NOT NULL
),
stats AS (
  SELECT
    count(*)::bigint AS total_pairs,
    count(*) FILTER (WHERE detail_address_key_matched)::bigint AS detail_address_matched_pairs,
    count(*) FILTER (WHERE covered)::bigint AS covered,
    count(*) FILTER (WHERE NOT covered)::bigint AS outside,
    count(*) FILTER (WHERE detail_address_key_matched AND covered)::bigint
      AS detail_address_matched_covered,
    count(*) FILTER (WHERE detail_address_key_matched AND NOT covered)::bigint
      AS detail_address_matched_outside
  FROM joined
),
sample AS (
  SELECT *
    FROM joined
   WHERE NOT covered
      OR NOT detail_address_key_matched
   ORDER BY covered ASC, detail_address_key_matched ASC
   LIMIT :sample_limit
)
SELECT
  stats.total_pairs,
  stats.detail_address_matched_pairs,
  stats.covered,
  stats.outside,
  stats.detail_address_matched_covered,
  stats.detail_address_matched_outside,
  CASE
    WHEN stats.total_pairs = 0 THEN NULL
    ELSE stats.covered::float8 / stats.total_pairs::float8
  END AS coverage_ratio,
  CASE
    WHEN stats.detail_address_matched_pairs = 0 THEN NULL
    ELSE stats.detail_address_matched_covered::float8
      / stats.detail_address_matched_pairs::float8
  END AS detail_address_matched_coverage_ratio,
  COALESCE((SELECT jsonb_agg(to_jsonb(sample)) FROM sample), '[]'::jsonb) AS sample
FROM stats
"""


async def drop_c13_detail_dong_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (
        C13_DETAIL_DONG_POLYGON_TABLE,
        C13_DETAIL_DONG_ENTRANCE_TABLE,
        C13_DETAIL_ADDRESS_TABLE,
    ),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table)}"))


def _detail_address_copy_sql(table_name: str) -> str:
    quoted = ", ".join(_quote_ident(column) for column in DETAIL_ADDRESS_COPY_COLUMNS)
    return f"COPY {_quote_ident_path(table_name)} ({quoted}) FROM STDIN"


def _detail_address_members(
    zip_file: zipfile.ZipFile,
    member_name: str | None,
) -> tuple[str, ...]:
    if member_name is not None:
        try:
            return (zip_member_case_sensitive(zip_file, member_name),)
        except KeyError as exc:
            msg = f"missing detail address member: {member_name}"
            raise LoaderError(msg) from exc
    return tuple(sorted(name for name in zip_file.namelist() if _is_detail_address_member(name)))


def zip_member_case_sensitive(zip_file: zipfile.ZipFile, member_name: str) -> str:
    names = set(zip_file.namelist())
    if member_name not in names:
        raise KeyError(member_name)
    return member_name


def _zip_members(path: Path) -> frozenset[str]:
    try:
        with zipfile.ZipFile(path) as zip_file:
            return frozenset(zip_file.namelist())
    except zipfile.BadZipFile as exc:
        msg = f"invalid detail address DB ZIP: {path}"
        raise LoaderError(msg) from exc


def _is_detail_address_member(name: str) -> bool:
    path = Path(name)
    return path.name.startswith("adrdc_") and path.suffix.lower() == ".txt"


def _blank_to_none(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _normalize_int_text(
    value: str,
    *,
    field_name: str,
    source_member: str,
    line_number: int,
) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    if not _UNSIGNED_INT_RE.fullmatch(stripped):
        msg = f"{source_member}:{line_number} {field_name} must be unsigned integer text"
        raise LoaderError(msg)
    return str(int(stripped))


def _road_name_no(road_name_cd: str | None) -> str | None:
    if road_name_cd is None:
        return None
    # 상세주소 DB의 도로명코드는 5자리 시군구 코드 뒤에 도로명 일련번호가 붙는다.
    if len(road_name_cd) <= 5:
        return road_name_cd
    return road_name_cd[5:]


def _covers_metrics(value: CoversMeasurement) -> dict[str, object]:
    return {
        "samples": value.samples,
        "covered": value.covered,
        "outside": value.outside,
        "coverage_ratio": value.coverage_ratio,
    }


def _detail_containment_metrics(
    value: DetailDongEntranceContainmentMeasurement,
) -> dict[str, object]:
    return {
        "total_pairs": value.total_pairs,
        "detail_address_matched_pairs": value.detail_address_matched_pairs,
        "covered": value.covered,
        "outside": value.outside,
        "detail_address_matched_covered": value.detail_address_matched_covered,
        "detail_address_matched_outside": value.detail_address_matched_outside,
        "coverage_ratio": value.coverage_ratio,
        "detail_address_matched_coverage_ratio": value.detail_address_matched_coverage_ratio,
    }


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
    return tuple(item for item in value if isinstance(item, dict))


def _optional_float(value: SupportsFloat | str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _alchemy_to_libpq(engine: AsyncEngine) -> str:
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _quote_ident_path(value: str) -> str:
    return ".".join(_quote_ident(part) for part in value.split("."))


def _quote_ident(value: str) -> str:
    if not _IDENT_RE.fullmatch(value):
        msg = f"invalid SQL identifier: {value!r}"
        raise LoaderError(msg)
    return f'"{value}"'
