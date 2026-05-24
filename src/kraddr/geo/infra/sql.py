"""Shared raw SQL fragments for schema and post-load operations."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS x_extension;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA x_extension;
SET search_path = public, x_extension;

CREATE TABLE IF NOT EXISTS tl_juso_text (
  bd_mgt_sn       TEXT PRIMARY KEY,
  sig_cd          TEXT NOT NULL,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  li_kor_nm       TEXT,
  bjd_cd          TEXT NOT NULL,
  adm_cd          TEXT,
  adm_kor_nm      TEXT,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn              TEXT,
  rn_nrm          TEXT GENERATED ALWAYS AS (
    regexp_replace(COALESCE(rn, ''), '\\s+', '', 'g')
  ) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  buld_nm         TEXT,
  buld_nm_nrm     TEXT GENERATED ALWAYS AS (
    regexp_replace(COALESCE(buld_nm, ''), '\\s+', '', 'g')
  ) STORED,
  mntn_yn         CHAR(1),
  lnbr_mnnm       INTEGER,
  lnbr_slno       INTEGER,
  zip_no          TEXT,
  pnu             TEXT GENERATED ALWAYS AS (
    CASE
      WHEN bjd_cd IS NULL
        OR mntn_yn IS NULL
        OR mntn_yn NOT IN ('0', '1')
        OR lnbr_mnnm IS NULL
      THEN NULL
      ELSE bjd_cd
        || CASE WHEN mntn_yn = '1' THEN '2' ELSE '1' END
        || lpad(lnbr_mnnm::text, 4, '0')
        || lpad(COALESCE(lnbr_slno, 0)::text, 4, '0')
    END
  ) STORED,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26),
  CHECK (char_length(sig_cd) = 5),
  CHECK (char_length(rn_cd) = 7),
  CHECK (char_length(bjd_cd) = 10)
);

CREATE TABLE IF NOT EXISTS tl_locsum_entrc (
  sig_cd          TEXT NOT NULL,
  ent_man_no      BIGINT NOT NULL,
  bd_mgt_sn       TEXT,
  bjd_cd          TEXT NOT NULL,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn              TEXT,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  zip_no          TEXT,
  buld_use        TEXT,
  ent_se_cd       CHAR(1),
  adm_kor_nm      TEXT,
  geom            geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, ent_man_no)
);

CREATE TABLE IF NOT EXISTS tl_navi_buld_centroid (
  bd_mgt_sn       TEXT PRIMARY KEY,
  bjd_cd          TEXT,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  sig_cd          TEXT,
  rn_cd           TEXT,
  rncode_full     TEXT GENERATED ALWAYS AS (
    CASE WHEN sig_cd IS NULL OR rn_cd IS NULL THEN NULL ELSE sig_cd || rn_cd END
  ) STORED,
  rn              TEXT,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  zip_no          TEXT,
  buld_nm         TEXT,
  buld_use        TEXT,
  adm_cd          TEXT,
  adm_kor_nm      TEXT,
  centroid_5179   geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_navi_entrc (
  sig_cd          TEXT NOT NULL,
  entry_no        BIGINT NOT NULL,
  bd_mgt_sn       TEXT,
  bjd_cd          TEXT,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  kind            TEXT NOT NULL CHECK (kind IN ('navi','vehicle','parcel','aux')),
  geom            geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, entry_no)
);

CREATE TABLE IF NOT EXISTS tl_scco_ctprvn (
  ctprvn_cd       TEXT PRIMARY KEY,
  ctp_kor_nm      TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_scco_sig (
  sig_cd          TEXT PRIMARY KEY,
  sig_kor_nm      TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_scco_emd (
  emd_cd          TEXT PRIMARY KEY,
  emd_kor_nm      TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_scco_li (
  li_cd           TEXT PRIMARY KEY,
  li_kor_nm       TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_kodis_bas (
  bas_mgt_sn      TEXT PRIMARY KEY,
  bas_id          TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_spbd_buld_polygon (
  bd_mgt_sn       TEXT PRIMARY KEY,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tl_sprd_manage (
  sig_cd          TEXT NOT NULL,
  rds_man_no      TEXT NOT NULL,
  rn_cd           TEXT,
  rncode_full     TEXT GENERATED ALWAYS AS (
    CASE WHEN rn_cd IS NULL THEN NULL ELSE sig_cd || rn_cd END
  ) STORED,
  rn              TEXT,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, rds_man_no)
);

CREATE TABLE IF NOT EXISTS tl_sprd_intrvl (
  sig_cd          TEXT NOT NULL,
  rds_man_no      TEXT NOT NULL,
  bsi_int_sn      TEXT NOT NULL,
  start_bsi_no    TEXT,
  end_bsi_no      TEXT,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, rds_man_no, bsi_int_sn)
);

CREATE TABLE IF NOT EXISTS tl_sprd_rw (
  sig_cd          TEXT NOT NULL,
  rw_sn           TEXT NOT NULL,
  rds_man_no      TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, rw_sn)
);

CREATE TABLE IF NOT EXISTS postal_pobox (
  bd_mgt_sn       TEXT PRIMARY KEY,
  zip_no          TEXT NOT NULL,
  rn_code         TEXT,
  pobox_kind      TEXT CHECK (pobox_kind IN ('PO','PG')),
  pobox_name      TEXT,
  pobox_no_mn     INTEGER,
  pobox_no_sl     INTEGER DEFAULT 0,
  si_nm           TEXT,
  sgg_nm          TEXT,
  emd_nm          TEXT,
  bjd_cd          TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS postal_bulk_delivery (
  bulk_id         BIGSERIAL PRIMARY KEY,
  zip_no          TEXT NOT NULL,
  bd_mgt_sn       TEXT,
  bulk_name       TEXT NOT NULL,
  detail          TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS load_manifest (
  table_name        TEXT PRIMARY KEY,
  last_full_load_at TIMESTAMPTZ,
  last_delta_at     TIMESTAMPTZ,
  last_mvmn_de      TEXT,
  row_count         BIGINT NOT NULL DEFAULT 0,
  source_zip        TEXT,
  source_checksum   TEXT,
  source_yyyymm     TEXT,
  source_set        JSONB,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS load_codes (
  code              TEXT PRIMARY KEY,
  action            TEXT NOT NULL CHECK (action IN ('insert','update','delete')),
  note              TEXT
);

INSERT INTO load_codes(code, action) VALUES
  ('31','insert'), ('33','insert'),
  ('34','update'), ('35','update'), ('36','update'),
  ('63','delete'), ('64','delete')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS load_jobs (
  job_id            TEXT PRIMARY KEY,
  kind              TEXT NOT NULL,
  payload           JSONB NOT NULL,
  state             TEXT NOT NULL CHECK (state IN ('queued','running','done','failed','cancelled')),
  load_batch_id     TEXT,
  parent_job_id     TEXT,
  progress          NUMERIC(5,4) NOT NULL DEFAULT 0.0 CHECK (progress >= 0 AND progress <= 1),
  current_stage     TEXT,
  source_yyyymm     TEXT,
  source_set        JSONB,
  source_checksum   TEXT,
  error_message     TEXT,
  log_tail          JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload_summary   JSONB,
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  heartbeat_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS load_consistency_reports (
  report_id         TEXT PRIMARY KEY,
  scope             TEXT NOT NULL,
  started_at        TIMESTAMPTZ NOT NULL,
  finished_at       TIMESTAMPTZ,
  source_set        JSONB NOT NULL,
  cases             JSONB NOT NULL,
  severity_max      TEXT NOT NULL CHECK (severity_max IN ('OK','INFO','WARN','ERROR')),
  generated_by      TEXT
);

CREATE TABLE IF NOT EXISTS geo_cache (
  cache_key         TEXT PRIMARY KEY,
  service           TEXT NOT NULL,
  payload           JSONB NOT NULL,
  hit_count         BIGINT NOT NULL DEFAULT 0,
  last_hit_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at        TIMESTAMPTZ NOT NULL
);
"""

INDEX_SQL = """
SET search_path = public, x_extension;

CREATE INDEX IF NOT EXISTS idx_juso_text_road
  ON tl_juso_text (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX IF NOT EXISTS idx_juso_text_jibun
  ON tl_juso_text (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX IF NOT EXISTS idx_juso_text_rn_trgm
  ON tl_juso_text USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_juso_text_buld_nm_trgm
  ON tl_juso_text USING GIN (buld_nm_nrm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_juso_text_pnu
  ON tl_juso_text (pnu) WHERE pnu IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_locsum_geom
  ON tl_locsum_entrc USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_locsum_bd
  ON tl_locsum_entrc (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_locsum_rep
  ON tl_locsum_entrc (bd_mgt_sn, ent_se_cd, ent_man_no) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_locsum_resolve
  ON tl_locsum_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no);

CREATE INDEX IF NOT EXISTS idx_navi_centroid_geom
  ON tl_navi_buld_centroid USING GIST (centroid_5179);
CREATE INDEX IF NOT EXISTS idx_navi_centroid_resolve
  ON tl_navi_buld_centroid (
    rncode_full, buld_se_cd, buld_mnnm, buld_slno, (left(bjd_cd, 8))
  );
CREATE INDEX IF NOT EXISTS idx_navi_entrc_geom
  ON tl_navi_entrc USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_navi_entrc_bd
  ON tl_navi_entrc (bd_mgt_sn, kind) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_navi_entrc_resolve
  ON tl_navi_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd);

CREATE INDEX IF NOT EXISTS idx_scco_ctprvn_geom ON tl_scco_ctprvn USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_scco_sig_geom ON tl_scco_sig USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_scco_emd_geom ON tl_scco_emd USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_scco_li_geom ON tl_scco_li USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_kodis_bas_geom ON tl_kodis_bas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_kodis_bas_id ON tl_kodis_bas (bas_id);
CREATE INDEX IF NOT EXISTS idx_spbd_buld_polygon_geom ON tl_spbd_buld_polygon USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sprd_rw_geom ON tl_sprd_rw USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sprd_manage_rn ON tl_sprd_manage (rncode_full);
CREATE INDEX IF NOT EXISTS idx_sprd_intrvl_rds ON tl_sprd_intrvl (sig_cd, rds_man_no);

CREATE INDEX IF NOT EXISTS idx_pobox_lookup
  ON postal_pobox (zip_no, pobox_kind, si_nm, sgg_nm);
CREATE INDEX IF NOT EXISTS idx_bulk_bd_mgt_sn
  ON postal_bulk_delivery (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bulk_zip
  ON postal_bulk_delivery (zip_no);

CREATE INDEX IF NOT EXISTS idx_load_jobs_state
  ON load_jobs (state) WHERE state IN ('queued','running');
CREATE INDEX IF NOT EXISTS idx_load_jobs_batch
  ON load_jobs (load_batch_id, created_at) WHERE load_batch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_load_jobs_parent
  ON load_jobs (parent_job_id) WHERE parent_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_load_jobs_created
  ON load_jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consistency_started
  ON load_consistency_reports (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_geo_cache_expires
  ON geo_cache (expires_at);
"""

MV_SQL = """
SET search_path = public, x_extension;

DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target;
CREATE MATERIALIZED VIEW mv_geocode_target AS
WITH best_entrc AS (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom AS ent_pt_5179
    FROM tl_locsum_entrc
   WHERE bd_mgt_sn IS NOT NULL
   ORDER BY bd_mgt_sn,
            CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END,
            ent_man_no
),
best_navi AS (
  SELECT DISTINCT ON (
         rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8)
         )
         rncode_full,
         buld_se_cd,
         buld_mnnm,
         buld_slno,
         left(bjd_cd, 8) AS bjd_emd_cd,
         centroid_5179
    FROM tl_navi_buld_centroid
   WHERE rncode_full IS NOT NULL
     AND bjd_cd IS NOT NULL
   ORDER BY rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8), bd_mgt_sn
)
SELECT
  j.bd_mgt_sn,
  j.rncode_full,
  j.rn,
  j.rn_nrm,
  j.buld_mnnm,
  j.buld_slno,
  j.buld_se_cd,
  j.buld_nm,
  j.buld_nm_nrm,
  j.bjd_cd,
  j.adm_cd,
  j.adm_kor_nm,
  j.mntn_yn,
  j.lnbr_mnnm,
  j.lnbr_slno,
  j.zip_no,
  j.ctp_kor_nm AS si_nm,
  j.sig_kor_nm AS sgg_nm,
  j.emd_kor_nm AS emd_nm,
  j.li_kor_nm AS li_nm,
  j.pnu,
  COALESCE(be.ent_pt_5179, nc.centroid_5179) AS pt_5179,
  CASE
    WHEN COALESCE(be.ent_pt_5179, nc.centroid_5179) IS NULL THEN NULL
    ELSE ST_Transform(COALESCE(be.ent_pt_5179, nc.centroid_5179), 4326)
  END AS pt_4326,
  CASE
    WHEN be.ent_pt_5179 IS NOT NULL THEN 'entrance'
    WHEN nc.centroid_5179 IS NOT NULL THEN 'centroid'
    ELSE NULL
  END AS pt_source
FROM tl_juso_text j
LEFT JOIN best_entrc be ON be.bd_mgt_sn = j.bd_mgt_sn
LEFT JOIN best_navi nc
  ON nc.rncode_full = j.rncode_full
 AND nc.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
 AND nc.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
 AND nc.buld_slno IS NOT DISTINCT FROM j.buld_slno
 AND nc.bjd_emd_cd = left(j.bjd_cd, 8)
WITH DATA;

CREATE UNIQUE INDEX idx_mv_geocode_target_pk ON mv_geocode_target (bd_mgt_sn);
CREATE INDEX idx_mv_road
  ON mv_geocode_target (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_mv_jibun
  ON mv_geocode_target (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX idx_mv_rn_trgm
  ON mv_geocode_target USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX idx_mv_buld_nm_trgm
  ON mv_geocode_target USING GIN (buld_nm_nrm gin_trgm_ops);
CREATE INDEX idx_mv_geom5179
  ON mv_geocode_target USING GIST (pt_5179) WHERE pt_5179 IS NOT NULL;
CREATE INDEX idx_mv_geom4326
  ON mv_geocode_target USING GIST (pt_4326) WHERE pt_4326 IS NOT NULL;
CREATE INDEX idx_mv_pt_source ON mv_geocode_target (pt_source);
"""

POSTLOAD_SQL = """
SET search_path = public, x_extension;

UPDATE tl_locsum_entrc e
   SET bd_mgt_sn = j.bd_mgt_sn
  FROM tl_juso_text j
 WHERE e.bd_mgt_sn IS NULL
   AND e.rncode_full = j.rncode_full
   AND e.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
   AND e.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
   AND e.buld_slno IS NOT DISTINCT FROM j.buld_slno
   AND e.bjd_cd = j.bjd_cd
   AND (e.zip_no IS NULL OR j.zip_no IS NULL OR e.zip_no = j.zip_no);

UPDATE tl_navi_entrc e
   SET bd_mgt_sn = j.bd_mgt_sn
  FROM tl_juso_text j
 WHERE e.bd_mgt_sn IS NULL
   AND e.rncode_full = j.rncode_full
   AND e.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
   AND e.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
   AND e.buld_slno IS NOT DISTINCT FROM j.buld_slno
   AND (e.bjd_cd IS NULL OR e.bjd_cd = j.bjd_cd);

ANALYZE tl_juso_text;
ANALYZE tl_locsum_entrc;
ANALYZE tl_navi_buld_centroid;
ANALYZE tl_navi_entrc;
"""


def iter_sql_statements(sql: str) -> tuple[str, ...]:
    """Return non-empty SQL statements split for simple migration execution."""

    return tuple(part.strip() for part in sql.split(";") if part.strip())
