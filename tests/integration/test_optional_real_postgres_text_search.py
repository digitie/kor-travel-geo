from __future__ import annotations

import os
from typing import Any

import pytest
from sqlalchemy import text

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.geocode_repo import _FUZZY_ROADS
from kraddr.geo.settings import Settings

_LEGACY_FUZZY_ROADS = text(
    """
SELECT bd_mgt_sn,
       similarity(rn_nrm, :road_nrm) AS confidence
  FROM mv_geocode_target
 WHERE (CAST(:si AS text) IS NULL OR si_nm = CAST(:si AS text))
   AND (CAST(:sgg AS text) IS NULL OR sgg_nm = CAST(:sgg AS text))
   AND (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
   AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
   AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
   AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
   AND rn_nrm % :road_nrm
   AND buld_mnnm = :mnnm
 ORDER BY similarity(rn_nrm, :road_nrm) DESC,
          CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END,
          bd_mgt_sn
 LIMIT :limit
"""
)


@pytest.mark.asyncio
async def test_real_postgres_text_search_mv_matches_legacy_fuzzy_order() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL text-search parity")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            helper = await conn.scalar(text("SELECT to_regclass('mv_geocode_text_search')"))
            if helper is None:
                pytest.skip("mv_geocode_text_search is not available")
            rows = (
                await conn.execute(
                    text(
                        """
SELECT si_nm, sgg_nm, rn_nrm, buld_mnnm, left(bjd_cd, 5) AS sig_cd
  FROM mv_geocode_target
 WHERE rn_nrm IS NOT NULL
   AND rn_nrm <> ''
   AND buld_mnnm IS NOT NULL
 ORDER BY bd_mgt_sn
 LIMIT 8
"""
                    )
                )
            ).mappings().all()
            assert rows
            await conn.commit()

            for row in rows:
                params: dict[str, Any] = {
                    "si": row["si_nm"],
                    "sgg": row["sgg_nm"],
                    "sig_cd_filter": None,
                    "sig_cd_prefix": None,
                    "bjd_cd_filter": None,
                    "bjd_cd_prefix": None,
                    "road_nrm": str(row["rn_nrm"])[: max(2, len(str(row["rn_nrm"])) - 1)],
                    "mnnm": row["buld_mnnm"],
                    "limit": 5,
                }
                legacy = await _fetch_fuzzy(conn, _LEGACY_FUZZY_ROADS, params)
                current = await _fetch_fuzzy(conn, _FUZZY_ROADS, params)
                assert current == legacy

                hinted_params = {
                    **params,
                    "si": None,
                    "sgg": None,
                    "sig_cd_filter": row["sig_cd"],
                }
                hinted_legacy = await _fetch_fuzzy(conn, _LEGACY_FUZZY_ROADS, hinted_params)
                hinted_current = await _fetch_fuzzy(conn, _FUZZY_ROADS, hinted_params)
                assert hinted_current == hinted_legacy
    finally:
        await engine.dispose()


async def _fetch_fuzzy(
    conn: Any,
    statement: Any,
    params: dict[str, Any],
) -> tuple[tuple[str, float], ...]:
    async with conn.begin():
        await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.42"))
        rows = (await conn.execute(statement, params)).mappings().all()
    return tuple((str(row["bd_mgt_sn"]), round(float(row["confidence"]), 6)) for row in rows)
