from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.geometry_repo import _BUILDING_GEOMETRY_SQL
from kortravelgeo.loaders.consistency import CASE_SQL
from kortravelgeo.loaders.data_quality import EXPORT_SPECS
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


@pytest.mark.asyncio
async def test_polygon_address_join_preserves_road_owner_and_building_identifiers():
    dsn = os.getenv('KTG_TEST_PG_DSN')
    if not dsn:
        pytest.skip('set KTG_TEST_PG_DSN to a disposable PostgreSQL database')
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            for name in ('tl_juso_text', 'tl_spbd_buld_polygon'):
                await conn.execute(text(
                    f'CREATE TEMP TABLE {name} (LIKE public.{name} '
                    'INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP'
                ))
            await conn.execute(text(
                'INSERT INTO tl_juso_text '
                '(bd_mgt_sn,sig_cd,bjd_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno) '
                "VALUES ('11200113410311300013100000','11200','1120011300',"
                "'4103113','0',131,0)"
            ))
            await conn.execute(text(
                'INSERT INTO tl_spbd_buld_polygon '
                '(bd_mgt_sn,sig_cd,emd_cd,li_cd,rds_sig_cd,rn_cd,'
                'buld_se_cd,buld_mnnm,buld_slno,geom) '
                "VALUES ('1120011300105560001010733','11200','113','00','11140',"
                "'4103113','0',131,0,ST_GeomFromText("
                "'MULTIPOLYGON(((953000 1952000,953010 1952000,953010 1952010,"
                "953000 1952010,953000 1952000)))',5179))"
            ))
            for code in ('C1', 'C2'):
                result = (await conn.execute(text(CASE_SQL[code].sql))).mappings().one()
                assert result['count'] == 0, (code, dict(result))
            params = {'bd_mgt_sn': None, 'bjd_cd': '1120011300',
                      'buld_mnnm': 131, 'buld_slno': 0, 'buld_se_cd': '0'}
            # 주소 소재 시군구와 도로 관할 시군구 중 어느 쪽 입력도 기존 도형을 찾는다.
            for road_code in ('112004103113', '111404103113'):
                row = (await conn.execute(
                    _BUILDING_GEOMETRY_SQL, params | {'rncode_full': road_code}
                )).mappings().one()
                assert row['bd_mgt_sn'] == '1120011300105560001010733'
                assert row['rncode_full'] == '111404103113'
            assert not (await conn.execute(
                _BUILDING_GEOMETRY_SQL,
                params | {'rncode_full': '112004103113', 'bjd_cd': '1120011400'}
            )).first()
            await conn.execute(text(
                'UPDATE tl_spbd_buld_polygon SET rds_sig_cd=NULL'
            ))
            result = (await conn.execute(text(CASE_SQL['C2'].sql))).mappings().one()
            assert result['count'] == 0, dict(result)
            samples_sql = next(s.sql for s in EXPORT_SPECS if s.filename == 'c2_samples.csv')
            summary_sql = next(s.sql for s in EXPORT_SPECS
                               if s.filename == 'c2_missing_key_summary.csv')
            assert not (await conn.execute(text(samples_sql), {'limit': 20})).first()
            assert (await conn.execute(text(summary_sql))).mappings().one()['rows'] == 0
            await conn.execute(text('UPDATE tl_spbd_buld_polygon SET rn_cd=NULL'))
            result = (await conn.execute(text(CASE_SQL['C2'].sql))).mappings().one()
            assert result['count'] == 1
            assert result['metric']['missing_resolve_key'] == 1
            assert (await conn.execute(text(samples_sql), {'limit': 20})).mappings().one()[
                'reason'
            ] == 'missing_resolve_key'
            assert (await conn.execute(text(summary_sql))).mappings().one()['rows'] == 1
    finally:
        await engine.dispose()
