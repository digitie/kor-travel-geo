from __future__ import annotations

from kraddr.geo.infra.engine import _connect_options, make_async_engine
from kraddr.geo.infra.pnu import build_pnu, pnu_land_type_from_mntn_yn
from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements
from kraddr.geo.settings import Settings


def test_engine_uses_settings_dsn_and_x_extension_search_path() -> None:
    settings = Settings(
        pg_dsn="postgresql://u:p@localhost:5432/kraddr_geo",
        pg_statement_timeout_ms=4321,
    )

    engine = make_async_engine(settings)

    assert str(engine.url).startswith("postgresql+psycopg://")
    assert "statement_timeout=4321" in _connect_options(settings)
    assert "search_path=public,x_extension" in _connect_options(settings)


def test_pnu_mapping_is_standard_and_null_safe() -> None:
    assert pnu_land_type_from_mntn_yn("0") == "1"
    assert pnu_land_type_from_mntn_yn("1") == "2"
    assert build_pnu(bjd_cd="1111010100", mntn_yn="0", lnbr_mnnm=144, lnbr_slno=3) == (
        "1111010100101440003"
    )
    assert build_pnu(bjd_cd="1111010100", mntn_yn="1", lnbr_mnnm=108, lnbr_slno=0) == (
        "1111010100201080000"
    )
    assert build_pnu(bjd_cd="1111010100", mntn_yn="0", lnbr_mnnm=None) is None


def test_schema_contracts_follow_adr_012_and_016() -> None:
    assert "CREATE SCHEMA IF NOT EXISTS x_extension" in SCHEMA_SQL
    assert "CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS tl_juso_text" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS tl_juso_parcel_link" in SCHEMA_SQL
    assert "REFERENCES tl_juso_text(bd_mgt_sn) ON DELETE CASCADE" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS tl_locsum_entrc" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS load_jobs" in SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS load_consistency_reports" in SCHEMA_SQL
    assert "COALESCE(lnbr_mnnm, 0)" not in SCHEMA_SQL
    assert "WHEN bjd_cd IS NULL" in SCHEMA_SQL
    assert "OR mntn_yn IS NULL" in SCHEMA_SQL
    assert "mntn_yn NOT IN ('0', '1')" in SCHEMA_SQL
    assert "CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26)" in SCHEMA_SQL
    assert "load_batch_id" in SCHEMA_SQL
    assert "parent_job_id" in SCHEMA_SQL
    assert "COALESCE(NULLIF(li_cd, ''), '00')" in SCHEMA_SQL
    assert "NULLIF(rds_sig_cd, '') IS NULL" in SCHEMA_SQL
    assert "NULLIF(rn_cd, '') IS NULL" in SCHEMA_SQL
    assert "idx_juso_parcel_link_pnu" in INDEX_SQL
    assert "idx_juso_parcel_link_road" in INDEX_SQL


def test_mv_contract_uses_pt_5179_and_partial_spatial_indexes() -> None:
    assert "pt_5179" in MV_SQL
    assert "pt_4326" in MV_SQL
    assert "pt_source" in MV_SQL
    assert "tl_locsum_entrc" in MV_SQL
    assert "tl_navi_buld_centroid" in MV_SQL
    assert "best_navi" in MV_SQL
    assert "left(bjd_cd, 8)" in MV_SQL
    assert "nc.bjd_emd_cd = left(j.bjd_cd, 8)" in MV_SQL
    assert "idx_mv_geom5179" in MV_SQL
    assert "WHERE pt_5179 IS NOT NULL" in MV_SQL
    assert "ent_pt_4326" not in MV_SQL
    assert "idx_juso_text_rn_trgm" in INDEX_SQL
    assert "idx_juso_text_resolve" in INDEX_SQL
    assert "rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no" in INDEX_SQL


def test_iter_sql_statements_preserves_semicolons_inside_literals_and_comments() -> None:
    sql = """
-- comment with ; should not split
SELECT ';' AS literal;
/* block ; comment */
SELECT 'it''s; ok' AS escaped;
DO $$ BEGIN RAISE NOTICE ';'; END $$;
SELECT "$not_dollar$;still_identifier";
"""

    statements = iter_sql_statements(sql)

    assert len(statements) == 4
    assert "SELECT ';' AS literal" in statements[0]
    assert "SELECT 'it''s; ok' AS escaped" in statements[1]
    assert "RAISE NOTICE ';'" in statements[2]
    assert 'SELECT "$not_dollar$;still_identifier"' in statements[3]
