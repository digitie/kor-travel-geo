"""보존한 공식 주소 행의 원문·식별자·정규화 경계."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kortravelgeo.core.normalize import parse_address
from kortravelgeo.loaders.text.juso_hangul_loader import parse_juso_row

FIXTURE = Path(__file__).parents[1] / "fixtures" / "juso_hahoe_202605.json"
EXPECTED_IDS = {
    (40, 0): "47170340472227900004000000",
    (40, 1): "47170340472227900004000001",
    (68, 0): "47170340472227900006800000",
}


def test_official_fixture_preserves_all_67_rows_and_cp949_bytes() -> None:
    data = json.loads(FIXTURE.read_text())
    assert data["source"]["source_yyyymm"] == "202605"
    assert len(data["rows"]) == data["source"]["row_count"] == 67
    excerpt = bytearray()
    ids = set()
    for item in data["rows"]:
        line = ("|".join(item["columns"]) + "\r\n").encode("cp949")
        assert hashlib.sha256(line).hexdigest() == item["line_sha256"]
        excerpt.extend(line)
        assert len(item["columns"][0]) == 26
        ids.add(item["columns"][0])
    assert len(ids) == 67
    assert hashlib.sha256(excerpt).hexdigest() == data["source"]["excerpt_sha256"]


def test_actual_loader_keeps_official_number_and_region_fields() -> None:
    data = json.loads(FIXTURE.read_text())
    matched = {}
    for item in data["rows"]:
        row = parse_juso_row(
            item["columns"],
            source_name=data["source"]["member"],
            line_no=item["source_line"],
            source_yyyymm="202605",
        )
        key = row.buld_mnnm, row.buld_slno
        if key in EXPECTED_IDS:
            matched[key] = row.bd_mgt_sn
            assert (row.ctp_kor_nm, row.sig_kor_nm, row.emd_kor_nm, row.li_kor_nm) == (
                "경상북도",
                "안동시",
                "풍천면",
                "하회리",
            )
            assert row.bjd_cd == "4717034033"
            assert row.adm_cd == "4717034000"
            assert row.buld_se_cd == "0"
            assert row.zip_no == "36760"
    assert matched == EXPECTED_IDS


def test_full_alias_and_canonical_query_keep_the_original_number() -> None:
    for province in ("경북", "경북도", "경상북도"):
        parts = parse_address(f"{province} 안동시 풍천면 하회종가길 40")
        assert (
            parts.si,
            parts.sgg,
            parts.emd,
            parts.road_nrm,
            parts.mnnm,
            parts.slno,
            parts.buld_se_cd,
        ) == (
            "경상북도",
            "안동시",
            "풍천면",
            "하회종가길",
            40,
            0,
            "0",
        )
