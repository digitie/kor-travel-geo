"""공식 원문→실제 COPY/generated columns/MV→repository→인증된 v2 HTTP.

기존 테스트 DB의 원천은 변경하지 않는다. guard를 통과한 테스트 cluster에 UUID
scratch DB를 만들며, 테스트가 직접 만든 DB만 종료 후 지운다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.api.app import create_app
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.scratch_db import ensure_scratch_database
from kortravelgeo.infra.search_repo import SearchRepository
from kortravelgeo.infra.sql import MV_SQL, TEXT_SEARCH_MV_SQL, iter_sql_statements
from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
from kortravelgeo.settings import Settings, get_settings
from tests.integration._pg_guard import require_disposable_database

FIXTURE = Path(__file__).parents[1] / "fixtures" / "juso_hahoe_202605.json"


@pytest.mark.asyncio
async def test_official_juso_rows_survive_loader_mv_and_v2_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS cluster")
    base = make_async_engine(Settings(_env_file=None, pg_dsn=dsn))
    try:
        await require_disposable_database(base)
    finally:
        await base.dispose()

    data = json.loads(FIXTURE.read_text())
    excerpt = b"".join(
        ("|".join(item["columns"]) + "\r\n").encode("cp949") for item in data["rows"]
    )
    assert hashlib.sha256(excerpt).hexdigest() == data["source"]["excerpt_sha256"]
    source = tmp_path / data["source"]["member"]
    source.write_bytes(excerpt)
    db_name = "geo_pinvi650_test_" + uuid4().hex
    maintenance = create_async_engine(
        make_url(dsn).set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    engine = None
    try:
        scratch_dsn = await ensure_scratch_database(Settings(_env_file=None, pg_dsn=dsn), db_name)
        fixture_key = "official-650-local-regression"
        settings = Settings(
            _env_file=None,
            pg_dsn=scratch_dsn,
            vworld_api_key=SecretStr(fixture_key),
        )
        engine = make_async_engine(settings)
        assert await load_juso_hangul(engine, source, source_yyyymm="202605") == 67
        # COPY와 serving 반영을 구별한다. 초기 scratch MV는 비어 있다.
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT count(*) FROM tl_juso_text")) == 67
            assert await conn.scalar(text("SELECT count(*) FROM mv_geocode_target")) == 0
        async with engine.begin() as conn:
            for group in (MV_SQL, TEXT_SEARCH_MV_SQL):
                for statement in iter_sql_statements(group):
                    await conn.execute(text(statement))
        repository = SearchRepository(engine)
        for query, expected in [
            ("경북 안동시 풍천면 하회종가길 40", "47170340472227900004000000"),
            ("경상북도 안동시 풍천면 하회종가길 40", "47170340472227900004000000"),
            ("경북 안동시 풍천면 하회종가길 40-1", "47170340472227900004000001"),
            ("경북 안동시 풍천면 하회종가길 68", "47170340472227900006800000"),
        ]:
            rows, total = await repository.search(query, search_type="address", page=1, size=8)
            assert total == 1
            assert [row.lookup.bd_mgt_sn for row in rows] == [expected]
            assert rows[0].lookup.point is None

        import kortravelgeo.api.app as app_module

        monkeypatch.setattr(app_module, "get_settings", lambda: settings)
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        async with AsyncAddressClient(settings, engine=engine) as client:
            app.state.client = client
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://owned-geo.test",
                headers={"X-KTG-API-Key": fixture_key},
            ) as http:
                for province in ("경북", "경상북도"):
                    for extra in ({}, {"type": "address"}):
                        query = f"{province} 안동시 풍천면 하회종가길 40"
                        response = await http.post(
                            "/v2/search", json={"query": query, "size": 8, **extra}
                        )
                        assert response.status_code == 200, response.text
                        payload = response.json()
                        assert payload["status"] == "OK" and payload["total"] == 1, payload
                        assert len(payload["candidates"]) == 1, payload
                        candidate = payload["candidates"][0]
                        assert candidate["address"]["full"].endswith("하회종가길 40"), payload
                        assert candidate.get("point") is None, payload
                for suffix in ("40-2", "999", "지하 40"):
                    response = await http.post(
                        "/v2/search",
                        json={
                            "query": f"경북 안동시 풍천면 하회종가길 {suffix}",
                            "type": "address",
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert response.json()["status"] == "NOT_FOUND", response.text
                    assert response.json()["total"] == 0, response.text
                # 없는 번호 조회 후 같은 client의 정상 주소도 계속 성공해야 한다.
                for body in [
                    {"query": "경상남도 안동시 풍천면 하회종가길 40"},
                    {"query": "경북 안동시 다른면 하회종가길 40"},
                    {"query": "경북 안동시 풍천면 하회종가길 40", "sig_cd": "11"},
                ]:
                    response = await http.post("/v2/search", json=body)
                    assert response.status_code == 200, response.text
                    assert response.json()["total"] == 0, response.text
                for suffix in ("40-1", "68", "40", "40"):
                    response = await http.post(
                        "/v2/search",
                        json={
                            "query": f"경북 안동시 풍천면 하회종가길 {suffix}",
                        },
                    )
                    assert response.status_code == 200, response.text
                    payload = response.json()
                    assert payload["status"] == "OK" and payload["total"] == 1, payload
                    assert payload["candidates"][0]["address"]["full"].endswith(
                        f"하회종가길 {suffix}"
                    ), payload
                response = await http.post("/v2/search", json={"query": "하회종가길", "size": 100})
                assert response.status_code == 200, response.text
                payload = response.json()
                assert payload["status"] == "OK" and payload["total"] == 67, payload
                assert len(response.json()["candidates"]) == 67
    finally:
        if engine is not None:
            await engine.dispose()
        # UUID로 이 시험이 만든 이름만 정리한다. base DB/다른 cluster에는 쓰지 않는다.
        assert re.fullmatch(r"geo_pinvi650_test_[0-9a-f]{32}", db_name)
        try:
            async with maintenance.connect() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        finally:
            await maintenance.dispose()
