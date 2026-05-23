from pathlib import Path

from kraddr.geo.loaders.juso_map import MASTER_LAYER_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = REPO_ROOT / "sql"

MASTER_TABLES = tuple(layer.lower() for layer in MASTER_LAYER_NAMES)


def _read_sql(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _squashed_sql(relative_path: str) -> str:
    return " ".join(_read_sql(relative_path).lower().split())


def test_extension_ddl_enables_required_postgres_extensions() -> None:
    sql = _squashed_sql("sql/ddl/001_extensions.sql")

    for extension in ("postgis", "pg_trgm", "unaccent"):
        assert f"create extension if not exists {extension}" in sql


def test_master_ddl_declares_all_electronic_map_layers() -> None:
    sql = _squashed_sql("sql/ddl/010_master_tables.sql")

    for table_name in MASTER_TABLES:
        assert f"create table if not exists {table_name}" in sql


def test_master_ddl_uses_expected_postgis_geometry_types_and_srid() -> None:
    sql = _squashed_sql("sql/ddl/010_master_tables.sql")

    assert "tl_scco_ctprvn" in sql and "geometry(multipolygon, 5179)" in sql
    assert "tl_kodis_bas" in sql and "geometry(multipolygon, 5179)" in sql
    assert "tl_sprd_rw" in sql and "geometry(multilinestring, 5179)" in sql
    assert "tl_spbd_buld" in sql and "geometry(multipolygon, 5179)" in sql
    assert "tl_spbd_entrc" in sql and "geometry(point, 5179)" in sql


def test_building_ddl_has_generated_match_keys_and_pnu_mapping() -> None:
    sql = _squashed_sql("sql/ddl/010_master_tables.sql")

    assert "bjd_cd text generated always as" in sql
    assert "sig_cd || emd_cd || coalesce(nullif(li_cd, ''), '00')" in sql
    assert "rncode_full text generated always as (sig_cd || rn_cd) stored" in sql
    assert "buld_nm_nrm text generated always as" in sql
    assert "mntn_yn text not null default '0' check (mntn_yn in ('0', '1'))" in sql
    assert "pnu text generated always as" in sql
    assert "case mntn_yn when '1' then '2' else '1' end" in sql
    assert "lpad(lnbr_mnnm::text, 4, '0')" in sql
    assert "lpad(coalesce(lnbr_slno, 0)::text, 4, '0')" in sql


def test_meta_ddl_persists_load_jobs_and_default_mvm_codes() -> None:
    sql = _squashed_sql("sql/ddl/030_meta_tables.sql")

    assert "create table if not exists load_manifest" in sql
    assert "create table if not exists load_jobs" in sql
    assert "payload jsonb not null" in sql
    assert "state text not null check" in sql
    assert "'pending', 'running', 'success', 'failed', 'cancelled'" in sql
    assert "progress numeric(5,4) not null default 0" in sql
    assert "create table if not exists load_codes" in sql
    for code, action in (
        ("31", "insert"),
        ("33", "insert"),
        ("34", "update"),
        ("35", "update"),
        ("36", "update"),
        ("63", "delete"),
        ("64", "delete"),
    ):
        assert f"('{code}', '{action}')" in sql


def test_indexes_cover_geocode_reverse_jobs_and_cache_paths() -> None:
    sql = _squashed_sql("sql/indexes.sql")

    for index_name in (
        "idx_buld_road_match",
        "idx_buld_jibun_match",
        "idx_buld_pnu",
        "idx_kodis_bas_geom",
        "idx_entrc_geom",
        "idx_sprd_manage_rn_trgm",
        "idx_bulk_bd_mgt_sn",
        "idx_load_jobs_state_created",
        "idx_geo_cache_expires",
    ):
        assert f"create index if not exists {index_name}" in sql

    assert "using gist (geom)" in sql
    assert "using gin (rn_nrm gin_trgm_ops)" in sql


def test_materialized_view_ddl_keeps_5179_and_4326_points_and_unique_index() -> None:
    sql = _squashed_sql("sql/mv.sql")

    assert "create materialized view if not exists mv_geocode_target as" in sql
    assert "ent.geom as ent_pt_5179" in sql
    assert "st_transform(ent.geom, 4326) as ent_pt_4326" in sql
    assert "with no data" in sql
    assert "create unique index if not exists idx_mv_geocode_target_pk" in sql
    assert "create index if not exists idx_mv_geom5179" in sql
    assert "using gist (ent_pt_5179)" in sql
    assert "create index if not exists idx_mv_geom4326" in sql


def test_postload_refreshes_materialized_view_concurrently() -> None:
    sql = _squashed_sql("sql/postload.sql")

    assert "refresh materialized view concurrently mv_geocode_target" in sql
    assert "analyze mv_geocode_target" in sql
    assert "set pg_trgm.similarity_threshold" not in sql
