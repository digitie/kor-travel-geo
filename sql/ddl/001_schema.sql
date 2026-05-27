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

CREATE TABLE IF NOT EXISTS tl_juso_parcel_link (
  bd_mgt_sn       TEXT NOT NULL REFERENCES tl_juso_text(bd_mgt_sn) ON DELETE CASCADE,
  pnu             TEXT NOT NULL,
  bjd_cd          TEXT NOT NULL,
  mntn_yn         CHAR(1) NOT NULL,
  lnbr_mnnm       INTEGER NOT NULL,
  lnbr_slno       INTEGER NOT NULL DEFAULT 0,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  source_kind     TEXT NOT NULL CHECK (source_kind IN ('jibun_full','daily_lnbr')),
  source_file     TEXT,
  source_yyyymm   TEXT,
  last_mvmn_de    TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bd_mgt_sn, pnu),
  CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26),
  CHECK (char_length(pnu) = 19),
  CHECK (char_length(bjd_cd) = 10),
  CHECK (mntn_yn IN ('0', '1')),
  CHECK (lnbr_mnnm >= 0),
  CHECK (lnbr_slno >= 0),
  CHECK (char_length(sig_cd) = 5),
  CHECK (char_length(rn_cd) = 7)
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

CREATE TABLE IF NOT EXISTS tl_roadaddr_entrc (
  bd_mgt_sn       TEXT NOT NULL,
  bjd_cd          TEXT NOT NULL,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  li_kor_nm       TEXT,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn              TEXT,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  zip_no          TEXT,
  notice_de       TEXT,
  raw_col_13      TEXT,
  ent_man_no      BIGINT,
  ent_source_cd   TEXT NOT NULL,
  ent_detail_cd   TEXT NOT NULL,
  geom            geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bd_mgt_sn),
  CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26),
  CHECK (char_length(bjd_cd) = 10),
  CHECK (char_length(sig_cd) = 5),
  CHECK (char_length(rn_cd) = 7),
  CHECK (zip_no IS NULL OR char_length(zip_no) = 5),
  CHECK (notice_de IS NULL OR char_length(notice_de) = 8)
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

CREATE TABLE IF NOT EXISTS tl_sppn_makarea (
  sig_cd          TEXT NOT NULL,
  makarea_id      TEXT NOT NULL,
  ntfc_yn         TEXT,
  makarea_nm      TEXT,
  ntfc_de         TEXT,
  mvm_res_cd      TEXT,
  mvmn_resn       TEXT,
  opert_de        TEXT,
  makarea_ar      NUMERIC(12,3),
  mvmn_desc       TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT NOT NULL,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id),
  CHECK (char_length(sig_cd) = 5),
  CHECK (btrim(makarea_id) <> '')
);

CREATE TABLE IF NOT EXISTS tl_spbd_buld_polygon (
  bd_mgt_sn       TEXT PRIMARY KEY,
  sig_cd          TEXT,
  emd_cd          TEXT,
  li_cd           TEXT,
  bjd_cd          TEXT GENERATED ALWAYS AS (
    CASE
      WHEN NULLIF(sig_cd, '') IS NULL OR NULLIF(emd_cd, '') IS NULL THEN NULL
      ELSE sig_cd || emd_cd || COALESCE(NULLIF(li_cd, ''), '00')
    END
  ) STORED,
  rds_sig_cd      TEXT,
  rn_cd           TEXT,
  rncode_full     TEXT GENERATED ALWAYS AS (
    CASE
      WHEN NULLIF(rds_sig_cd, '') IS NULL OR NULLIF(rn_cd, '') IS NULL THEN NULL
      ELSE rds_sig_cd || rn_cd
    END
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
    CASE
      WHEN NULLIF(sig_cd, '') IS NULL OR NULLIF(rn_cd, '') IS NULL THEN NULL
      ELSE sig_cd || rn_cd
    END
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

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.audit_events (
  event_id          UUID PRIMARY KEY,
  occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_type        TEXT NOT NULL CHECK (actor_type IN ('system','cli','api','ui','scheduler')),
  actor_id          TEXT,
  client_ip_hash    TEXT,
  user_agent_hash   TEXT,
  request_id        TEXT,
  trace_id          TEXT,
  action            TEXT NOT NULL,
  resource_type     TEXT,
  resource_id       TEXT,
  job_id            TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  outcome           TEXT NOT NULL CHECK (outcome IN ('started','succeeded','failed','cancelled','denied')),
  error_code        TEXT,
  payload_redacted  JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload_hash      TEXT NOT NULL CHECK (char_length(payload_hash) = 64),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION ops.audit_events_append_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'ops.audit_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_ops_audit_events_append_only ON ops.audit_events;
CREATE TRIGGER trg_ops_audit_events_append_only
  BEFORE UPDATE OR DELETE ON ops.audit_events
  FOR EACH ROW EXECUTE FUNCTION ops.audit_events_append_only();

CREATE TABLE IF NOT EXISTS ops.dataset_snapshots (
  snapshot_id                 UUID PRIMARY KEY,
  state                       TEXT NOT NULL CHECK (state IN ('building','validated','rejected','released','retired')),
  parent_snapshot_id          UUID REFERENCES ops.dataset_snapshots(snapshot_id) ON DELETE SET NULL,
  source_set                  JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_set_hash             TEXT NOT NULL CHECK (char_length(source_set_hash) = 64),
  git_commit                  TEXT,
  alembic_revision            TEXT,
  postgres_version            TEXT,
  postgis_version             TEXT,
  row_counts                  JSONB NOT NULL DEFAULT '{}'::jsonb,
  table_stats_artifact_id     UUID,
  consistency_report_id       TEXT REFERENCES load_consistency_reports(report_id) ON DELETE SET NULL,
  performance_artifact_id     UUID,
  backup_artifact_id          UUID,
  created_by_job_id           TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at                TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.serving_releases (
  release_id                  UUID PRIMARY KEY,
  snapshot_id                 UUID NOT NULL REFERENCES ops.dataset_snapshots(snapshot_id) ON DELETE RESTRICT,
  state                       TEXT NOT NULL CHECK (state IN ('pending','active','superseded','rolled_back','failed')),
  release_kind                TEXT NOT NULL CHECK (release_kind IN ('full_load','daily_delta','restore','manual_rebuild','rollback')),
  previous_release_id         UUID REFERENCES ops.serving_releases(release_id) ON DELETE SET NULL,
  rollback_target_release_id  UUID REFERENCES ops.serving_releases(release_id) ON DELETE SET NULL,
  mv_name                     TEXT NOT NULL DEFAULT 'mv_geocode_target',
  mv_hash                     TEXT,
  consistency_gate            JSONB NOT NULL DEFAULT '{}'::jsonb,
  performance_gate            JSONB NOT NULL DEFAULT '{}'::jsonb,
  activated_by_job_id         TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  activated_at                TIMESTAMPTZ,
  notes                       TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.artifacts (
  artifact_id                 UUID PRIMARY KEY,
  artifact_type               TEXT NOT NULL CHECK (artifact_type IN (
                                'db_backup','db_restore_log','consistency_report',
                                'data_quality_export','perf_report','source_inventory',
                                'schema_diff','openapi_snapshot','other'
                              )),
  state                       TEXT NOT NULL CHECK (state IN ('creating','available','failed','deleted','expired')),
  storage_kind                TEXT NOT NULL CHECK (storage_kind IN ('local_file','s3','gcs','none')),
  storage_uri                 TEXT,
  display_name                TEXT,
  media_type                  TEXT,
  compression                 TEXT,
  size_bytes                  BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
  sha256                      TEXT CHECK (sha256 IS NULL OR char_length(sha256) = 64),
  retention_class             TEXT,
  expires_at                  TIMESTAMPTZ,
  job_id                      TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  snapshot_id                 UUID REFERENCES ops.dataset_snapshots(snapshot_id) ON DELETE SET NULL,
  release_id                  UUID REFERENCES ops.serving_releases(release_id) ON DELETE SET NULL,
  manifest                    JSONB NOT NULL DEFAULT '{}'::jsonb,
  download_token_hash         TEXT,
  callback_url                TEXT,
  callback_state              TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at                 TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.maintenance_windows (
  window_id                   UUID PRIMARY KEY,
  kind                        TEXT NOT NULL CHECK (kind IN ('full_load','restore','schema_migration','mv_refresh','read_only','exclusive')),
  state                       TEXT NOT NULL CHECK (state IN ('scheduled','active','ending','ended','cancelled','failed')),
  starts_at                   TIMESTAMPTZ,
  ends_at                     TIMESTAMPTZ,
  actual_started_at           TIMESTAMPTZ,
  actual_ended_at             TIMESTAMPTZ,
  reason                      TEXT NOT NULL,
  requested_by                TEXT,
  approved_by                 TEXT,
  confirmation_hash           TEXT NOT NULL CHECK (char_length(confirmation_hash) = 64),
  blocks                      JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by_job_id           TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  closed_by_job_id            TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.table_stats_snapshots (
  stats_id                    UUID PRIMARY KEY,
  snapshot_id                 UUID REFERENCES ops.dataset_snapshots(snapshot_id) ON DELETE SET NULL,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  schema_name                 TEXT NOT NULL,
  object_name                 TEXT NOT NULL,
  object_kind                 TEXT NOT NULL CHECK (object_kind IN ('table','materialized_view','index','toast','other')),
  estimated_rows              BIGINT CHECK (estimated_rows IS NULL OR estimated_rows >= 0),
  exact_rows                  BIGINT CHECK (exact_rows IS NULL OR exact_rows >= 0),
  total_bytes                 BIGINT CHECK (total_bytes IS NULL OR total_bytes >= 0),
  table_bytes                 BIGINT CHECK (table_bytes IS NULL OR table_bytes >= 0),
  index_bytes                 BIGINT CHECK (index_bytes IS NULL OR index_bytes >= 0),
  toast_bytes                 BIGINT CHECK (toast_bytes IS NULL OR toast_bytes >= 0),
  dead_tuples                 BIGINT CHECK (dead_tuples IS NULL OR dead_tuples >= 0),
  last_vacuum                 TIMESTAMPTZ,
  last_analyze                TIMESTAMPTZ,
  stats                       JSONB NOT NULL DEFAULT '{}'::jsonb
);
