-- Generated mirror of src/kraddr/geo/infra/sql.py for review/DBA use.

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
    regexp_replace(COALESCE(rn, ''), '\s+', '', 'g')
  ) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  buld_nm         TEXT,
  buld_nm_nrm     TEXT GENERATED ALWAYS AS (
    regexp_replace(COALESCE(buld_nm, ''), '\s+', '', 'g')
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
  sig_cd          TEXT,
  emd_cd          TEXT,
  li_cd           TEXT,
  bjd_cd          TEXT GENERATED ALWAYS AS (
    CASE
      WHEN sig_cd IS NULL OR emd_cd IS NULL OR li_cd IS NULL THEN NULL
      ELSE sig_cd || emd_cd || li_cd
    END
  ) STORED,
  rds_sig_cd      TEXT,
  rn_cd           TEXT,
  rncode_full     TEXT GENERATED ALWAYS AS (
    CASE WHEN rds_sig_cd IS NULL OR rn_cd IS NULL THEN NULL ELSE rds_sig_cd || rn_cd END
  ) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
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
  geom            geometry(MultiLineString, 5179),
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
