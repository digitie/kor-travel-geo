"""Mapping helpers for raw SQL repository rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, Literal

from kraddr.geo.core.protocols import (
    AddressLookup,
    ConsistencyCaseRow,
    ConsistencyReportRow,
    LoadJobRow,
    PoboxLookup,
    ReverseLookup,
    SearchLookup,
    SppnAreaLookup,
    ZipLookup,
)
from kraddr.geo.dto.common import Point, ZipSource


def _point(row: Mapping[str, Any]) -> Point | None:
    lon = row.get("lon")
    lat = row.get("lat")
    if lon is None or lat is None:
        return None
    return Point(x=float(lon), y=float(lat))


def address_text(row: Mapping[str, Any], *, address_type: Literal["road", "parcel"]) -> str:
    if address_type == "road":
        base = " ".join(
            part
            for part in (
                row.get("si_nm"),
                row.get("sgg_nm"),
                row.get("road_nm") or row.get("rn"),
                _building_detail(row),
            )
            if part
        )
    else:
        lot = _lot_detail(row)
        base = " ".join(
            part
            for part in (
                row.get("si_nm"),
                row.get("sgg_nm"),
                row.get("emd_nm"),
                row.get("li_nm"),
                lot,
            )
            if part
        )
    return base.strip()


def _building_detail(row: Mapping[str, Any]) -> str | None:
    main = row.get("buld_mnnm")
    if main is None:
        return None
    sub = int(row.get("buld_slno") or 0)
    prefix = "지하 " if row.get("buld_se_cd") == "1" else ""
    return f"{prefix}{int(main)}-{sub}" if sub else f"{prefix}{int(main)}"


def _lot_detail(row: Mapping[str, Any]) -> str | None:
    main = row.get("lnbr_mnnm")
    if main is None:
        return None
    sub = int(row.get("lnbr_slno") or 0)
    prefix = "산 " if row.get("mntn_yn") == "1" else ""
    return f"{prefix}{int(main)}-{sub}" if sub else f"{prefix}{int(main)}"


def map_address(
    row: Mapping[str, Any],
    *,
    address_type: Literal["road", "parcel"],
) -> AddressLookup:
    text = address_text(row, address_type=address_type)
    return AddressLookup(
        bd_mgt_sn=str(row["bd_mgt_sn"]),
        text=text,
        address_type=address_type,
        point=_point(row),
        si_nm=row.get("si_nm"),
        sgg_nm=row.get("sgg_nm"),
        emd_nm=row.get("emd_nm"),
        li_nm=row.get("li_nm"),
        road_nm=row.get("road_nm") or row.get("rn"),
        detail=_building_detail(row) if address_type == "road" else _lot_detail(row),
        rncode_full=row.get("rncode_full"),
        bjd_cd=row.get("bjd_cd"),
        adm_cd=row.get("adm_cd"),
        adm_nm=row.get("adm_kor_nm"),
        zip_no=row.get("zip_no"),
        buld_nm=row.get("buld_nm"),
        pt_source=row.get("pt_source"),
        confidence=float(row.get("confidence") or 1.0),
    )


def map_reverse(
    row: Mapping[str, Any],
    *,
    address_type: Literal["road", "parcel"],
) -> ReverseLookup:
    base = map_address(row, address_type=address_type)
    return ReverseLookup(**asdict(base), distance_m=float(row["distance_m"]))


def map_sppn_area(row: Mapping[str, Any]) -> SppnAreaLookup:
    area_m2 = row.get("area_m2")
    return SppnAreaLookup(
        sig_cd=str(row["sig_cd"]),
        makarea_id=str(row["makarea_id"]),
        makarea_nm=row.get("makarea_nm"),
        ntfc_yn=row.get("ntfc_yn"),
        ntfc_de=row.get("ntfc_de"),
        mvm_res_cd=row.get("mvm_res_cd"),
        source_file=row.get("source_file"),
        source_yyyymm=row.get("source_yyyymm"),
        area_m2=float(area_m2) if area_m2 is not None else None,
        point=_point(row),
    )


def map_search(row: Mapping[str, Any]) -> SearchLookup:
    lookup = map_address(row, address_type="road")
    return SearchLookup(
        type="address",
        title=lookup.text,
        address=lookup.text,
        lookup=lookup,
        score=float(row["score"]) if row.get("score") is not None else None,
    )


def map_region_search(row: Mapping[str, Any]) -> SearchLookup:
    title = str(row["title"])
    score = float(row["score"]) if row.get("score") is not None else None
    lookup = AddressLookup(
        bd_mgt_sn=f"region:{row['code']}",
        text=title,
        address_type="road",
        point=_point(row),
        si_nm=row.get("si_nm"),
        sgg_nm=row.get("sgg_nm"),
        emd_nm=row.get("emd_nm"),
        li_nm=row.get("li_nm"),
        bjd_cd=row.get("region_code"),
        confidence=score or 0.0,
    )
    return SearchLookup(
        type="district",
        title=title,
        address=title,
        lookup=lookup,
        score=score,
    )


def map_zip(row: Mapping[str, Any]) -> ZipLookup:
    return ZipLookup(
        zip_no=str(row["zip_no"]),
        source=ZipSource(str(row["source"])),
        address=row.get("address"),
        bd_mgt_sn=row.get("bd_mgt_sn"),
        detail=row.get("detail"),
    )


def map_pobox(row: Mapping[str, Any]) -> PoboxLookup:
    return PoboxLookup(
        zip_no=str(row["zip_no"]),
        pobox_kind=row["pobox_kind"],
        pobox_name=row.get("pobox_name"),
        pobox_no_mn=row.get("pobox_no_mn"),
        pobox_no_sl=row.get("pobox_no_sl"),
        si_nm=row.get("si_nm"),
        sgg_nm=row.get("sgg_nm"),
        emd_nm=row.get("emd_nm"),
        bjd_cd=row.get("bjd_cd"),
    )


def map_load_job(row: Mapping[str, Any]) -> LoadJobRow:
    return LoadJobRow(
        job_id=str(row["job_id"]),
        kind=str(row["kind"]),
        state=row["state"],
        load_batch_id=row.get("load_batch_id"),
        parent_job_id=row.get("parent_job_id"),
        progress=float(row.get("progress") or 0.0),
        current_stage=row.get("current_stage"),
        source_yyyymm=row.get("source_yyyymm"),
        source_set=row.get("source_set"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        heartbeat_at=row.get("heartbeat_at"),
        error_message=row.get("error_message"),
        log_tail=tuple(row.get("log_tail") or ()),
        payload_summary=row.get("payload_summary"),
    )


def map_consistency_case(raw: Mapping[str, Any]) -> ConsistencyCaseRow:
    return ConsistencyCaseRow(
        code=str(raw["code"]),
        name=str(raw["name"]),
        severity=raw["severity"],
        count=int(raw.get("count") or 0),
        ratio=raw.get("ratio"),
        threshold=raw.get("threshold"),
        metric=raw.get("metric"),
        sample=tuple(raw.get("sample") or ()),
        note=raw.get("note"),
    )


def map_consistency_report(row: Mapping[str, Any]) -> ConsistencyReportRow:
    raw_cases = row.get("cases") or []
    cases = tuple(map_consistency_case(case) for case in raw_cases)
    return ConsistencyReportRow(
        report_id=str(row["report_id"]),
        scope=str(row["scope"]),
        severity_max=row["severity_max"],
        source_set=row["source_set"],
        started_at=row["started_at"],
        finished_at=row.get("finished_at"),
        cases=cases,
        generated_by=row.get("generated_by") or "api",
    )
