"""C1의 두 도로 코드·NULL 비교와 후보 비교량을 생성 입력으로 검증한다."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.consistency import CASE_SQL
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


def _inputs(size: int, varied: bool) -> tuple[list[dict], list[dict]]:
    addresses = []
    buildings = []
    for g in range(1, size + 1):
        code = f"{g:07d}"
        full = "31110" + code
        address = {
            "bd_mgt_sn": f"주소-{g:05d}",
            "sig_cd": "31110",
            "rn": f"생성도로{g}길",
            "rncode_full": None if varied and g % 19 == 0 else full,
            "bjd_cd": None if varied and g % 31 == 0 else "3111011400",
            "buld_se_cd": None if varied and g % 7 == 0 else "0",
            "buld_mnnm": None if varied and g % 11 == 0 else g,
            "buld_slno": None if varied and g % 13 == 0 else 0,
        }
        building = {
            key: address[key] for key in ("bjd_cd", "buld_se_cd", "buld_mnnm", "buld_slno")
        }
        building.update(
            bd_mgt_sn=f"건물-{g:05d}",
            rncode_full=None if g % 6 == 0 else full if g % 6 in (1, 4, 5) else "99999" + code,
            sig_cd=(
                None
                if varied and g % 23 == 0
                else "31110" if g % 6 in (0, 2, 4, 5) else "99999"
            ),
            rn_cd=code,
        )
        if varied and g % 29 == 0:
            building["bjd_cd"] = None
        elif g % 6 == 4:
            building["bjd_cd"] = "3111011500"
        addresses.append(address)
        buildings.append(building)
        if g % 17 == 0:
            buildings.append(dict(building, bd_mgt_sn=f"중복주소건물-{g:05d}"))
    return addresses, buildings


def _matches(address: dict, building: dict) -> bool:
    legacy = (
        None
        if building["sig_cd"] is None or building["rn_cd"] is None
        else building["sig_cd"] + building["rn_cd"]
    )
    road_matches = (
        address["rncode_full"] is not None
        and address["rncode_full"] in (building["rncode_full"], legacy)
    )
    return (
        road_matches
        and address["bjd_cd"] is not None
        and building["bjd_cd"] == address["bjd_cd"]
        and all(
            address[key] == building[key] for key in ("buld_se_cd", "buld_mnnm", "buld_slno")
        )
    )


def _selection() -> str:
    # 실제 테이블 이름을 CTE로 가려 원천 행을 읽지 않는다.
    return (
        """
WITH
tl_juso_text AS MATERIALIZED (
 SELECT * FROM jsonb_to_recordset(CAST(:addresses AS jsonb)) AS a(
  bd_mgt_sn text,sig_cd text,rn text,rncode_full text,bjd_cd text,
  buld_se_cd text,buld_mnnm integer,buld_slno integer)
),
tl_spbd_buld_polygon AS MATERIALIZED (
 SELECT * FROM jsonb_to_recordset(CAST(:buildings AS jsonb)) AS b(
  bd_mgt_sn text,rncode_full text,sig_cd text,rn_cd text,bjd_cd text,
  buld_se_cd text,buld_mnnm integer,buld_slno integer)
),
"""
        + CASE_SQL["C1"].sql.strip()[4:]
    )


@asynccontextmanager
async def _connection():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            yield conn
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("varied", [False, True])
async def test_both_road_codes_null_house_keys_and_duplicate_buildings(varied):
    addresses, buildings = _inputs(180, varied)
    expected = {
        address["bd_mgt_sn"]: {
            key: address[key] for key in ("bd_mgt_sn", "sig_cd", "rn", "buld_mnnm", "buld_slno")
        }
        for address in addresses
        if not any(_matches(address, building) for building in buildings)
    }
    async with _connection() as conn:
        result = (
            await conn.execute(
                text(_selection()),
                {"addresses": json.dumps(addresses), "buildings": json.dumps(buildings)},
            )
        ).mappings().one()
    assert result["count"] == len(expected)
    assert result["total"] == len(addresses)
    assert result["metric"] == {}
    assert len(result["sample"]) == min(20, len(expected))
    assert len({row["bd_mgt_sn"] for row in result["sample"]}) == len(result["sample"])
    assert all(row == expected[row["bd_mgt_sn"]] for row in result["sample"])


@pytest.mark.asyncio
async def test_same_dong_does_not_compare_unrelated_roads():
    addresses, buildings = _inputs(1500, True)
    async with _connection() as conn:
        plan = (
            await conn.execute(
                text("EXPLAIN (ANALYZE,FORMAT JSON) " + _selection()),
                {"addresses": json.dumps(addresses), "buildings": json.dumps(buildings)},
            )
        ).scalar_one()

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    walked = list(nodes(plan[0]["Plan"]))
    assert not any(
        node.get("Relation Name") in ("tl_juso_text", "tl_spbd_buld_polygon") for node in walked
    )
    removed = sum(
        node.get("Rows Removed by Join Filter", 0) * node.get("Actual Loops", 0)
        for node in walked
    )
    # 시간에 의존하지 않고 같은 법정동의 무관한 도로를 전량 비교하는 회귀를 막는다.
    assert removed < 4 * len(addresses)
