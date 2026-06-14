"""C16 address/building DB row and key drift validation prototype."""

from __future__ import annotations

import re
import zipfile
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
    StagingKeyIndexSpec,
    _jsonb_sample,
    _quote_ident,
    _quote_ident_path,
    create_staging_key_indexes,
    measure_key_overlap,
)
from kortravelgeo.loaders.text.common import TextSource, as_int, iter_pipe_rows, required

C16_ADDRESS_DB_SOURCE_KEY = "address_db_full"
C16_BUILDING_DB_SOURCE_KEY = "building_db_full"

C16_ADDRESS_DB_ADDRESS_TABLE = "_ktg_c16_address_db_address"
C16_ADDRESS_DB_EXTRA_TABLE = "_ktg_c16_address_db_extra"
C16_ADDRESS_DB_JIBUN_TABLE = "_ktg_c16_address_db_jibun"
C16_BUILDING_DB_BUILD_TABLE = "_ktg_c16_building_db_build"
C16_BUILDING_DB_JIBUN_TABLE = "_ktg_c16_building_db_jibun"

_SQL_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\s*\([^;]*\))?$")


@dataclass(frozen=True, slots=True)
class AddressDbMembers:
    address: tuple[TextSource, ...]
    extra: tuple[TextSource, ...]
    jibun: tuple[TextSource, ...]
    road_code: TextSource | None

    @property
    def counts(self) -> dict[str, int]:
        return {
            "address_members": len(self.address),
            "extra_members": len(self.extra),
            "jibun_members": len(self.jibun),
            "road_code_members": 1 if self.road_code is not None else 0,
        }

    @property
    def missing_kinds(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.address:
            missing.append("주소_*.txt")
        if not self.extra:
            missing.append("부가정보_*.txt")
        if not self.jibun:
            missing.append("지번_*.txt")
        if self.road_code is None:
            missing.append("개선_도로명코드_전체분.txt")
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class BuildingDbMembers:
    build: tuple[TextSource, ...]
    jibun: tuple[TextSource, ...]
    road_code: TextSource | None

    @property
    def counts(self) -> dict[str, int]:
        return {
            "build_members": len(self.build),
            "jibun_members": len(self.jibun),
            "road_code_members": 1 if self.road_code is not None else 0,
        }

    @property
    def missing_kinds(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.build:
            missing.append("build_*.txt")
        if not self.jibun:
            missing.append("jibun_*.txt")
        if self.road_code is None:
            missing.append("road_code_total.txt")
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class AddressDbAddressRow:
    source_file: str
    line_no: int
    bd_mgt_sn: str
    rncode_full: str
    sig_cd: str
    rn_cd: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    zip_no: str | None

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.bd_mgt_sn,
            self.rncode_full,
            self.sig_cd,
            self.rn_cd,
            self.buld_se_cd,
            self.buld_mnnm,
            self.buld_slno,
            self.zip_no,
        )


@dataclass(frozen=True, slots=True)
class AddressDbExtraRow:
    source_file: str
    line_no: int
    bd_mgt_sn: str
    adm_cd: str | None
    adm_nm: str | None
    zip_no: str | None
    buld_nm: str | None

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.bd_mgt_sn,
            self.adm_cd,
            self.adm_nm,
            self.zip_no,
            self.buld_nm,
        )


@dataclass(frozen=True, slots=True)
class AddressDbJibunRow:
    source_file: str
    line_no: int
    bd_mgt_sn: str
    pnu: str
    bjd_cd: str
    mntn_yn: str
    lnbr_mnnm: int
    lnbr_slno: int

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.bd_mgt_sn,
            self.pnu,
            self.bjd_cd,
            self.mntn_yn,
            self.lnbr_mnnm,
            self.lnbr_slno,
        )


@dataclass(frozen=True, slots=True)
class BuildingDbBuildRow:
    source_file: str
    line_no: int
    bd_mgt_sn: str
    bjd_cd: str
    rncode_full: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None
    zip_no: str | None

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.bd_mgt_sn,
            self.bjd_cd,
            self.rncode_full,
            self.buld_se_cd,
            self.buld_mnnm,
            self.buld_slno,
            self.zip_no,
        )


@dataclass(frozen=True, slots=True)
class BuildingDbJibunRow:
    source_file: str
    line_no: int
    pnu: str
    bjd_cd: str
    mntn_yn: str
    lnbr_mnnm: int
    lnbr_slno: int
    rncode_full: str
    buld_se_cd: str | None
    buld_mnnm: int | None
    buld_slno: int | None

    def copy_tuple(self) -> tuple[object, ...]:
        return (
            self.source_file,
            self.line_no,
            self.pnu,
            self.bjd_cd,
            self.mntn_yn,
            self.lnbr_mnnm,
            self.lnbr_slno,
            self.rncode_full,
            self.buld_se_cd,
            self.buld_mnnm,
            self.buld_slno,
        )


@dataclass(frozen=True, slots=True)
class TextStagingColumn:
    name: str
    sql_type: str = "text"


@dataclass(frozen=True, slots=True)
class TextStagingSpec:
    table_name: str
    columns: tuple[TextStagingColumn, ...]


@dataclass(frozen=True, slots=True)
class C16StagingRows:
    address_db_address: int
    address_db_extra: int
    address_db_jibun: int
    building_db_build: int
    building_db_jibun: int

    def metrics(self) -> dict[str, int]:
        return {
            "address_db_address": self.address_db_address,
            "address_db_extra": self.address_db_extra,
            "address_db_jibun": self.address_db_jibun,
            "building_db_build": self.building_db_build,
            "building_db_jibun": self.building_db_jibun,
        }


@dataclass(frozen=True, slots=True)
class C16KeyDriftComparison:
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
class C16AddressBuildingDriftComparison:
    address_db_zip: str
    building_db_zip: str
    source_yyyymm: str | None
    address_members: AddressDbMembers
    building_members: BuildingDbMembers
    staging_rows: C16StagingRows
    comparisons: tuple[C16KeyDriftComparison, ...]
    limit_per_member: int | None = None

    def metrics(self) -> dict[str, object]:
        return {
            "address_db_zip": self.address_db_zip,
            "building_db_zip": self.building_db_zip,
            "source_yyyymm": self.source_yyyymm,
            "source_members": {
                "address_db": self.address_members.counts,
                "building_db": self.building_members.counts,
            },
            "staging_rows": self.staging_rows.metrics(),
            "limit_per_member": self.limit_per_member,
            "comparisons": {
                comparison.name: comparison.metrics() for comparison in self.comparisons
            },
            "notes": (
                "address_db_full and building_db_full are row/key drift validation "
                "sources. C16 stages selected text keys and compares them with "
                "tl_juso_text, tl_juso_parcel_link, and tl_spbd_buld_polygon; "
                "it does not load coordinates or promote either source into "
                "serving candidates."
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


def discover_address_db_members(zip_path: Path | str) -> AddressDbMembers:
    sources = _zip_text_sources(Path(zip_path))
    return AddressDbMembers(
        address=tuple(source for source in sources if _is_named_member(source, "주소_")),
        extra=tuple(source for source in sources if _is_named_member(source, "부가정보_")),
        jibun=tuple(source for source in sources if _is_named_member(source, "지번_")),
        road_code=next(
            (
                source
                for source in sources
                if source.name == "개선_도로명코드_전체분.txt"
            ),
            None,
        ),
    )


def discover_building_db_members(zip_path: Path | str) -> BuildingDbMembers:
    sources = _zip_text_sources(Path(zip_path))
    return BuildingDbMembers(
        build=tuple(source for source in sources if source.name.startswith("build_")),
        jibun=tuple(source for source in sources if source.name.startswith("jibun_")),
        road_code=next(
            (source for source in sources if source.name == "road_code_total.txt"),
            None,
        ),
    )


def iter_address_db_address_rows(
    zip_path: Path | str,
    *,
    limit_per_member: int | None = None,
) -> Iterator[AddressDbAddressRow]:
    members = discover_address_db_members(zip_path)
    _raise_if_missing(members.missing_kinds, source_key=C16_ADDRESS_DB_SOURCE_KEY)
    for source in members.address:
        for index, (line_no, row) in enumerate(
            iter_pipe_rows(source, min_columns=11, encoding="cp949")
        ):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_address_db_address_row(row, source_name=source.name, line_no=line_no)


def parse_address_db_address_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
) -> AddressDbAddressRow:
    bd_mgt_sn = required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    rncode_full = _required_rncode_full(row[1], source_name=source_name, line_no=line_no)
    return AddressDbAddressRow(
        source_file=source_name,
        line_no=line_no,
        bd_mgt_sn=bd_mgt_sn,
        rncode_full=rncode_full,
        sig_cd=rncode_full[:5],
        rn_cd=rncode_full[5:],
        buld_se_cd=row[3] or None,
        buld_mnnm=as_int(row[4]),
        buld_slno=as_int(row[5]),
        zip_no=row[6] or None,
    )


def iter_address_db_extra_rows(
    zip_path: Path | str,
    *,
    limit_per_member: int | None = None,
) -> Iterator[AddressDbExtraRow]:
    members = discover_address_db_members(zip_path)
    _raise_if_missing(members.missing_kinds, source_key=C16_ADDRESS_DB_SOURCE_KEY)
    for source in members.extra:
        for index, (line_no, row) in enumerate(
            iter_pipe_rows(source, min_columns=9, encoding="cp949")
        ):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_address_db_extra_row(row, source_name=source.name, line_no=line_no)


def parse_address_db_extra_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
) -> AddressDbExtraRow:
    return AddressDbExtraRow(
        source_file=source_name,
        line_no=line_no,
        bd_mgt_sn=required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no),
        adm_cd=row[1] or None,
        adm_nm=row[2] or None,
        zip_no=row[3] or None,
        buld_nm=row[6] or None,
    )


def iter_address_db_jibun_rows(
    zip_path: Path | str,
    *,
    limit_per_member: int | None = None,
) -> Iterator[AddressDbJibunRow]:
    members = discover_address_db_members(zip_path)
    _raise_if_missing(members.missing_kinds, source_key=C16_ADDRESS_DB_SOURCE_KEY)
    for source in members.jibun:
        for index, (line_no, row) in enumerate(
            iter_pipe_rows(source, min_columns=11, encoding="cp949")
        ):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_address_db_jibun_row(row, source_name=source.name, line_no=line_no)


def parse_address_db_jibun_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
) -> AddressDbJibunRow:
    bd_mgt_sn = required(row[0], field="bd_mgt_sn", source_name=source_name, line_no=line_no)
    bjd_cd = required(row[2], field="bjd_cd", source_name=source_name, line_no=line_no)
    mntn_yn = required(row[7], field="mntn_yn", source_name=source_name, line_no=line_no)
    lnbr_mnnm = _required_int(row[8], field="lnbr_mnnm", source_name=source_name, line_no=line_no)
    lnbr_slno = as_int(row[9]) or 0
    pnu = _build_pnu(
        bjd_cd=bjd_cd,
        mntn_yn=mntn_yn,
        lnbr_mnnm=lnbr_mnnm,
        lnbr_slno=lnbr_slno,
        source_name=source_name,
        line_no=line_no,
    )
    return AddressDbJibunRow(
        source_file=source_name,
        line_no=line_no,
        bd_mgt_sn=bd_mgt_sn,
        pnu=pnu,
        bjd_cd=bjd_cd,
        mntn_yn=mntn_yn,
        lnbr_mnnm=lnbr_mnnm,
        lnbr_slno=lnbr_slno,
    )


def iter_building_db_build_rows(
    zip_path: Path | str,
    *,
    limit_per_member: int | None = None,
) -> Iterator[BuildingDbBuildRow]:
    members = discover_building_db_members(zip_path)
    _raise_if_missing(members.missing_kinds, source_key=C16_BUILDING_DB_SOURCE_KEY)
    for source in members.build:
        for index, (line_no, row) in enumerate(
            iter_pipe_rows(source, min_columns=31, encoding="cp949")
        ):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_building_db_build_row(row, source_name=source.name, line_no=line_no)


def parse_building_db_build_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
) -> BuildingDbBuildRow:
    bjd_cd = required(row[0], field="bjd_cd", source_name=source_name, line_no=line_no)
    rncode_full = _required_rncode_full(row[8], source_name=source_name, line_no=line_no)
    return BuildingDbBuildRow(
        source_file=source_name,
        line_no=line_no,
        bd_mgt_sn=required(row[15], field="bd_mgt_sn", source_name=source_name, line_no=line_no),
        bjd_cd=bjd_cd,
        rncode_full=rncode_full,
        buld_se_cd=row[10] or None,
        buld_mnnm=as_int(row[11]),
        buld_slno=as_int(row[12]),
        zip_no=row[19] or None,
    )


def iter_building_db_jibun_rows(
    zip_path: Path | str,
    *,
    limit_per_member: int | None = None,
) -> Iterator[BuildingDbJibunRow]:
    members = discover_building_db_members(zip_path)
    _raise_if_missing(members.missing_kinds, source_key=C16_BUILDING_DB_SOURCE_KEY)
    for source in members.jibun:
        for index, (line_no, row) in enumerate(
            iter_pipe_rows(source, min_columns=14, encoding="cp949")
        ):
            if limit_per_member is not None and index >= limit_per_member:
                break
            yield parse_building_db_jibun_row(row, source_name=source.name, line_no=line_no)


def parse_building_db_jibun_row(
    row: list[str],
    *,
    source_name: str,
    line_no: int,
) -> BuildingDbJibunRow:
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
    return BuildingDbJibunRow(
        source_file=source_name,
        line_no=line_no,
        pnu=pnu,
        bjd_cd=bjd_cd,
        mntn_yn=mntn_yn,
        lnbr_mnnm=lnbr_mnnm,
        lnbr_slno=lnbr_slno,
        rncode_full=rncode_full,
        buld_se_cd=row[9] or None,
        buld_mnnm=as_int(row[10]),
        buld_slno=as_int(row[11]),
    )


def address_db_address_staging_spec(
    table_name: str = C16_ADDRESS_DB_ADDRESS_TABLE,
) -> TextStagingSpec:
    return TextStagingSpec(
        table_name=table_name,
        columns=(
            TextStagingColumn("source_file"),
            TextStagingColumn("line_no", "bigint"),
            TextStagingColumn("bd_mgt_sn"),
            TextStagingColumn("rncode_full"),
            TextStagingColumn("sig_cd"),
            TextStagingColumn("rn_cd"),
            TextStagingColumn("buld_se_cd"),
            TextStagingColumn("buld_mnnm", "integer"),
            TextStagingColumn("buld_slno", "integer"),
            TextStagingColumn("zip_no"),
        ),
    )


def address_db_extra_staging_spec(
    table_name: str = C16_ADDRESS_DB_EXTRA_TABLE,
) -> TextStagingSpec:
    return TextStagingSpec(
        table_name=table_name,
        columns=(
            TextStagingColumn("source_file"),
            TextStagingColumn("line_no", "bigint"),
            TextStagingColumn("bd_mgt_sn"),
            TextStagingColumn("adm_cd"),
            TextStagingColumn("adm_nm"),
            TextStagingColumn("zip_no"),
            TextStagingColumn("buld_nm"),
        ),
    )


def address_db_jibun_staging_spec(
    table_name: str = C16_ADDRESS_DB_JIBUN_TABLE,
) -> TextStagingSpec:
    return TextStagingSpec(
        table_name=table_name,
        columns=(
            TextStagingColumn("source_file"),
            TextStagingColumn("line_no", "bigint"),
            TextStagingColumn("bd_mgt_sn"),
            TextStagingColumn("pnu"),
            TextStagingColumn("bjd_cd"),
            TextStagingColumn("mntn_yn"),
            TextStagingColumn("lnbr_mnnm", "integer"),
            TextStagingColumn("lnbr_slno", "integer"),
        ),
    )


def building_db_build_staging_spec(
    table_name: str = C16_BUILDING_DB_BUILD_TABLE,
) -> TextStagingSpec:
    return TextStagingSpec(
        table_name=table_name,
        columns=(
            TextStagingColumn("source_file"),
            TextStagingColumn("line_no", "bigint"),
            TextStagingColumn("bd_mgt_sn"),
            TextStagingColumn("bjd_cd"),
            TextStagingColumn("rncode_full"),
            TextStagingColumn("buld_se_cd"),
            TextStagingColumn("buld_mnnm", "integer"),
            TextStagingColumn("buld_slno", "integer"),
            TextStagingColumn("zip_no"),
        ),
    )


def building_db_jibun_staging_spec(
    table_name: str = C16_BUILDING_DB_JIBUN_TABLE,
) -> TextStagingSpec:
    return TextStagingSpec(
        table_name=table_name,
        columns=(
            TextStagingColumn("source_file"),
            TextStagingColumn("line_no", "bigint"),
            TextStagingColumn("pnu"),
            TextStagingColumn("bjd_cd"),
            TextStagingColumn("mntn_yn"),
            TextStagingColumn("lnbr_mnnm", "integer"),
            TextStagingColumn("lnbr_slno", "integer"),
            TextStagingColumn("rncode_full"),
            TextStagingColumn("buld_se_cd"),
            TextStagingColumn("buld_mnnm", "integer"),
            TextStagingColumn("buld_slno", "integer"),
        ),
    )


def c16_staging_index_specs(
    *,
    address_table: str = C16_ADDRESS_DB_ADDRESS_TABLE,
    extra_table: str = C16_ADDRESS_DB_EXTRA_TABLE,
    address_jibun_table: str = C16_ADDRESS_DB_JIBUN_TABLE,
    building_table: str = C16_BUILDING_DB_BUILD_TABLE,
    building_jibun_table: str = C16_BUILDING_DB_JIBUN_TABLE,
) -> tuple[StagingKeyIndexSpec, ...]:
    return (
        StagingKeyIndexSpec(
            table_name=address_table,
            index_name="_idx_ktg_c16_address_bd",
            columns=("bd_mgt_sn",),
        ),
        StagingKeyIndexSpec(
            table_name=extra_table,
            index_name="_idx_ktg_c16_extra_bd",
            columns=("bd_mgt_sn",),
        ),
        StagingKeyIndexSpec(
            table_name=address_jibun_table,
            index_name="_idx_ktg_c16_address_jibun_bd_pnu",
            columns=("bd_mgt_sn", "pnu"),
        ),
        StagingKeyIndexSpec(
            table_name=building_table,
            index_name="_idx_ktg_c16_building_natural",
            columns=tuple(key.left for key in _BUILDING_NATURAL_KEYS),
        ),
        StagingKeyIndexSpec(
            table_name=building_jibun_table,
            index_name="_idx_ktg_c16_building_jibun_pnu_road",
            columns=("pnu", "rncode_full", "buld_se_cd", "buld_mnnm", "buld_slno"),
        ),
    )


async def compare_c16_address_building_drift(
    engine: AsyncEngine,
    address_db_zip: Path | str,
    building_db_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    limit_per_member: int | None = None,
    address_table: str = C16_ADDRESS_DB_ADDRESS_TABLE,
    extra_table: str = C16_ADDRESS_DB_EXTRA_TABLE,
    address_jibun_table: str = C16_ADDRESS_DB_JIBUN_TABLE,
    building_table: str = C16_BUILDING_DB_BUILD_TABLE,
    building_jibun_table: str = C16_BUILDING_DB_JIBUN_TABLE,
) -> C16AddressBuildingDriftComparison:
    address_path = Path(address_db_zip)
    building_path = Path(building_db_zip)
    address_members = discover_address_db_members(address_path)
    building_members = discover_building_db_members(building_path)
    _raise_if_missing(address_members.missing_kinds, source_key=C16_ADDRESS_DB_SOURCE_KEY)
    _raise_if_missing(building_members.missing_kinds, source_key=C16_BUILDING_DB_SOURCE_KEY)

    address_spec = address_db_address_staging_spec(address_table)
    extra_spec = address_db_extra_staging_spec(extra_table)
    address_jibun_spec = address_db_jibun_staging_spec(address_jibun_table)
    building_spec = building_db_build_staging_spec(building_table)
    building_jibun_spec = building_db_jibun_staging_spec(building_jibun_table)
    await recreate_text_staging_tables(
        engine,
        (
            address_spec,
            extra_spec,
            address_jibun_spec,
            building_spec,
            building_jibun_spec,
        ),
    )
    staging_rows = C16StagingRows(
        address_db_address=await copy_text_rows_to_staging(
            engine,
            address_spec,
            (
                row.copy_tuple()
                for row in iter_address_db_address_rows(
                    address_path,
                    limit_per_member=limit_per_member,
                )
            ),
        ),
        address_db_extra=await copy_text_rows_to_staging(
            engine,
            extra_spec,
            (
                row.copy_tuple()
                for row in iter_address_db_extra_rows(
                    address_path,
                    limit_per_member=limit_per_member,
                )
            ),
        ),
        address_db_jibun=await copy_text_rows_to_staging(
            engine,
            address_jibun_spec,
            (
                row.copy_tuple()
                for row in iter_address_db_jibun_rows(
                    address_path,
                    limit_per_member=limit_per_member,
                )
            ),
        ),
        building_db_build=await copy_text_rows_to_staging(
            engine,
            building_spec,
            (
                row.copy_tuple()
                for row in iter_building_db_build_rows(
                    building_path,
                    limit_per_member=limit_per_member,
                )
            ),
        ),
        building_db_jibun=await copy_text_rows_to_staging(
            engine,
            building_jibun_spec,
            (
                row.copy_tuple()
                for row in iter_building_db_jibun_rows(
                    building_path,
                    limit_per_member=limit_per_member,
                )
            ),
        ),
    )
    await create_staging_key_indexes(
        engine,
        c16_staging_index_specs(
            address_table=address_table,
            extra_table=extra_table,
            address_jibun_table=address_jibun_table,
            building_table=building_table,
            building_jibun_table=building_jibun_table,
        ),
    )
    comparisons = (
        await _measure_comparison(
            engine,
            name="address_db_address_to_tl_juso_text_bd_mgt_sn",
            left_source="address_db_full.주소_*.txt",
            left_table=address_table,
            right_source="tl_juso_text",
            right_table="tl_juso_text",
            key_contract="bd_mgt_sn",
            join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"),),
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="address_db_extra_to_tl_juso_text_bd_mgt_sn",
            left_source="address_db_full.부가정보_*.txt",
            left_table=extra_table,
            right_source="tl_juso_text",
            right_table="tl_juso_text",
            key_contract="bd_mgt_sn",
            join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"),),
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="address_db_jibun_to_tl_juso_parcel_link_bd_pnu",
            left_source="address_db_full.지번_*.txt",
            left_table=address_jibun_table,
            right_source="tl_juso_parcel_link",
            right_table="tl_juso_parcel_link",
            key_contract="bd_mgt_sn_pnu",
            join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"), JoinKey("pnu", "pnu")),
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="building_db_build_to_tl_spbd_buld_polygon_natural_key",
            left_source="building_db_full.build_*.txt",
            left_table=building_table,
            right_source="tl_spbd_buld_polygon",
            right_table="tl_spbd_buld_polygon",
            key_contract="rncode_buld_bjd",
            join_keys=_BUILDING_NATURAL_KEYS,
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="building_db_build_to_tl_juso_text_natural_key",
            left_source="building_db_full.build_*.txt",
            left_table=building_table,
            right_source="tl_juso_text",
            right_table="tl_juso_text",
            key_contract="rncode_buld_bjd",
            join_keys=_BUILDING_NATURAL_KEYS,
            sample_limit=sample_limit,
        ),
        await _measure_comparison(
            engine,
            name="building_db_jibun_to_tl_juso_parcel_link_pnu_road_key",
            left_source="building_db_full.jibun_*.txt",
            left_table=building_jibun_table,
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
    return C16AddressBuildingDriftComparison(
        address_db_zip=str(address_path),
        building_db_zip=str(building_path),
        source_yyyymm=source_yyyymm,
        address_members=address_members,
        building_members=building_members,
        staging_rows=staging_rows,
        comparisons=comparisons,
        limit_per_member=limit_per_member,
    )


async def build_c16_address_building_drift_report(
    engine: AsyncEngine,
    address_db_zip: Path | str,
    building_db_zip: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    limit_per_member: int | None = None,
    generated_at: datetime | None = None,
) -> AugmentReport:
    try:
        comparison = await compare_c16_address_building_drift(
            engine,
            address_db_zip,
            building_db_zip,
            source_yyyymm=source_yyyymm,
            sample_limit=sample_limit,
            limit_per_member=limit_per_member,
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
    else:
        payload = comparison.to_payload()
        result = AugmentGroupResult(
            group_id="national",
            sido_name="전국",
            status="used",
            metrics=payload.metrics,
            sample=payload.sample,
            source_yyyymm=payload.source_yyyymm,
        )
    return AugmentReport(
        task_id="T-116",
        title="C16 address/building DB row-key drift validation",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=(result,),
        source_yyyymm=source_yyyymm,
    )


async def recreate_text_staging_tables(
    engine: AsyncEngine,
    specs: Sequence[TextStagingSpec],
) -> None:
    async with engine.begin() as conn:
        for spec in specs:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(spec.table_name)}"))
            await conn.execute(text(text_staging_create_sql(spec)))


def text_staging_create_sql(spec: TextStagingSpec) -> str:
    columns = ", ".join(
        f"{_quote_ident(column.name)} {_sql_type(column.sql_type)}"
        for column in spec.columns
    )
    return f"CREATE TABLE {_quote_ident_path(spec.table_name)} ({columns})"


async def copy_text_rows_to_staging(
    engine: AsyncEngine,
    spec: TextStagingSpec,
    rows: Iterable[Sequence[object]],
) -> int:
    copied = 0
    async with await psycopg.AsyncConnection.connect(
        _alchemy_to_libpq(engine),
        autocommit=False,
    ) as conn, conn.cursor() as cur:
        async with cur.copy(text_staging_copy_sql(spec)) as copy:
            for row in rows:
                await copy.write_row(row)
                copied += 1
        await conn.commit()
    return copied


def text_staging_copy_sql(spec: TextStagingSpec) -> str:
    columns = ", ".join(_quote_ident(column.name) for column in spec.columns)
    return f"COPY {_quote_ident_path(spec.table_name)} ({columns}) FROM STDIN"


async def measure_key_drift(
    engine: AsyncEngine,
    left_table: str,
    right_table: str,
    key_pairs: Sequence[JoinKey],
    *,
    sample_limit: int = 20,
) -> tuple[KeyOverlapMeasurement, tuple[Mapping[str, object], ...]]:
    overlap = await measure_key_overlap(engine, left_table, right_table, key_pairs)
    sql = key_drift_sample_sql(left_table, right_table, key_pairs)
    async with engine.connect() as conn:
        sample_value = await conn.scalar(text(sql), {"sample_limit": sample_limit})
    return overlap, _jsonb_sample(sample_value)


def key_drift_sample_sql(
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


async def drop_c16_address_building_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (
        C16_ADDRESS_DB_ADDRESS_TABLE,
        C16_ADDRESS_DB_EXTRA_TABLE,
        C16_ADDRESS_DB_JIBUN_TABLE,
        C16_BUILDING_DB_BUILD_TABLE,
        C16_BUILDING_DB_JIBUN_TABLE,
    ),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_quote_ident_path(table)}"))


_BUILDING_NATURAL_KEYS: tuple[JoinKey, ...] = (
    JoinKey("rncode_full", "rncode_full"),
    JoinKey("buld_se_cd", "buld_se_cd"),
    JoinKey("buld_mnnm", "buld_mnnm"),
    JoinKey("buld_slno", "buld_slno"),
    JoinKey("bjd_cd", "bjd_cd"),
)


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
) -> C16KeyDriftComparison:
    overlap, sample = await measure_key_drift(
        engine,
        left_table,
        right_table,
        join_keys,
        sample_limit=sample_limit,
    )
    return C16KeyDriftComparison(
        name=name,
        left_source=left_source,
        right_source=right_source,
        key_contract=key_contract,
        join_keys=join_keys,
        overlap=overlap,
        sample=sample,
    )


def _zip_text_sources(path: Path) -> tuple[TextSource, ...]:
    if not path.is_file():
        msg = f"ZIP source path does not exist: {path}"
        raise LoaderError(msg)
    with zipfile.ZipFile(path) as archive:
        sources = [
            TextSource(
                path=path,
                name=_recover_zip_member_name(info.filename),
                size=info.file_size,
                member_name=info.filename,
            )
            for info in archive.infolist()
            if not info.is_dir() and _recover_zip_member_name(info.filename).endswith(".txt")
        ]
    return tuple(sorted(sources, key=lambda source: source.name))


def _recover_zip_member_name(name: str) -> str:
    try:
        return name.encode("cp437").decode("cp949")
    except UnicodeError:
        return name


def _is_named_member(source: TextSource, prefix: str) -> bool:
    return source.name.startswith(prefix) and source.name.endswith(".txt")


def _raise_if_missing(missing: Sequence[str], *, source_key: str) -> None:
    if missing:
        msg = f"{source_key} missing required member(s): " + ", ".join(missing)
        raise LoaderError(msg)


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


def _sql_type(value: str) -> str:
    normalized = " ".join(value.split())
    if not _SQL_TYPE_RE.fullmatch(normalized):
        msg = f"invalid staging SQL type: {value!r}"
        raise LoaderError(msg)
    return normalized
