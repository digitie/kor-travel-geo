"""Shared raw SQL fragments for schema and post-load operations."""

from __future__ import annotations

import re

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS x_extension;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA x_extension;
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
  sigungu_buld_nm TEXT,
  sigungu_buld_nm_nrm TEXT GENERATED ALWAYS AS (
    regexp_replace(COALESCE(sigungu_buld_nm, ''), '\\s+', '', 'g')
  ) STORED,
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

CREATE TABLE IF NOT EXISTS region_radius_parts (
  level           TEXT NOT NULL CHECK (level IN ('sido','sigungu','emd')),
  code            TEXT NOT NULL,
  name            TEXT,
  parent_sido_cd  TEXT,
  parent_sig_cd   TEXT,
  part_no         INTEGER NOT NULL,
  geom            geometry(Geometry, 5179) NOT NULL,
  refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (level, code, part_no)
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
  executor          TEXT NOT NULL DEFAULT 'api_in_process'
                      CHECK (executor IN ('api_in_process','dagster')),
  orchestrator_run_id TEXT,
  lease_expires_at  TIMESTAMPTZ,
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
  audit_event_id    UUID PRIMARY KEY,
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
  job_id            TEXT REFERENCES load_jobs(job_id) ON DELETE NO ACTION,
  outcome           TEXT NOT NULL CHECK (
                    outcome IN ('started','succeeded','failed','cancelled','denied')
                  ),
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

CREATE TABLE IF NOT EXISTS ops.consistency_case_samples (
  sample_id            UUID PRIMARY KEY,
  report_id            TEXT NOT NULL REFERENCES load_consistency_reports(report_id)
                       ON DELETE CASCADE,
  case_code            TEXT NOT NULL CHECK (case_code ~ '^C\\d+$'),
  severity             TEXT NOT NULL CHECK (severity IN ('OK','INFO','WARN','ERROR')),
  sample_rank          INTEGER NOT NULL DEFAULT 0 CHECK (sample_rank >= 0),
  bd_mgt_sn            TEXT,
  rncode_full          TEXT,
  sig_cd               TEXT,
  bjd_cd               TEXT,
  distance_m           DOUBLE PRECISION,
  source_yyyymm        TEXT,
  source_kind          TEXT,
  case_metric          JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,
  point_4326           geometry(Point, 4326),
  point_5179           geometry(Point, 5179),
  bbox_4326            JSONB NOT NULL DEFAULT '{}'::jsonb,
  has_polygon          BOOLEAN NOT NULL DEFAULT false,
  has_line             BOOLEAN NOT NULL DEFAULT false,
  decision_state       TEXT NOT NULL DEFAULT 'unreviewed'
                       CHECK (decision_state IN ('unreviewed','approved','rejected','deferred')),
  reason_code          TEXT,
  note                 TEXT,
  reviewed_by          TEXT,
  reviewed_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.dataset_snapshots (
  dataset_snapshot_id         UUID PRIMARY KEY,
  state                       TEXT NOT NULL CHECK (
                              state IN ('building','validated','rejected','released','retired')
                            ),
  parent_dataset_snapshot_id  UUID REFERENCES ops.dataset_snapshots(dataset_snapshot_id)
                              ON DELETE SET NULL,
  source_set                  JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_set_hash             TEXT NOT NULL CHECK (char_length(source_set_hash) = 64),
  git_commit                  TEXT,
  alembic_revision            TEXT,
  postgres_version            TEXT,
  postgis_version             TEXT,
  row_counts                  JSONB NOT NULL DEFAULT '{}'::jsonb,
  table_stats_artifact_id     UUID,
  consistency_report_id       TEXT REFERENCES load_consistency_reports(report_id)
                              ON DELETE SET NULL,
  performance_artifact_id     UUID,
  backup_artifact_id          UUID,
  source_match_set_id         UUID,
  created_by_job_id           TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at                TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.serving_releases (
  serving_release_id          UUID PRIMARY KEY,
  dataset_snapshot_id         UUID NOT NULL REFERENCES ops.dataset_snapshots(dataset_snapshot_id)
                              ON DELETE RESTRICT,
  state                       TEXT NOT NULL CHECK (
                              state IN ('pending','active','superseded','rolled_back','failed')
                            ),
  release_kind                TEXT NOT NULL CHECK (
                              release_kind IN (
                                'full_load','daily_delta','restore','manual_rebuild','rollback'
                              )
                            ),
  previous_serving_release_id UUID REFERENCES ops.serving_releases(serving_release_id)
                              ON DELETE SET NULL,
  rollback_target_serving_release_id
                              UUID REFERENCES ops.serving_releases(serving_release_id)
                              ON DELETE SET NULL,
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
  state                       TEXT NOT NULL CHECK (
                              state IN ('creating','available','failed','deleted','expired')
                            ),
  storage_kind                TEXT NOT NULL CHECK (
                              storage_kind IN ('local_file','s3','gcs','none')
                            ),
  storage_uri                 TEXT,
  display_name                TEXT,
  media_type                  TEXT,
  compression                 TEXT,
  size_bytes                  BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
  sha256                      TEXT CHECK (sha256 IS NULL OR char_length(sha256) = 64),
  retention_class             TEXT,
  expires_at                  TIMESTAMPTZ,
  job_id                      TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  dataset_snapshot_id         UUID REFERENCES ops.dataset_snapshots(dataset_snapshot_id)
                              ON DELETE SET NULL,
  serving_release_id          UUID REFERENCES ops.serving_releases(serving_release_id)
                              ON DELETE SET NULL,
  manifest                    JSONB NOT NULL DEFAULT '{}'::jsonb,
  download_token_hash         TEXT,
  callback_url                TEXT,
  callback_state              TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at                 TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ops.maintenance_windows (
  maintenance_window_id       UUID PRIMARY KEY,
  kind                        TEXT NOT NULL CHECK (
                              kind IN (
                                'full_load','restore','schema_migration',
                                'mv_refresh','read_only','exclusive'
                              )
                            ),
  state                       TEXT NOT NULL CHECK (
                              state IN ('scheduled','active','ending','ended','cancelled','failed')
                            ),
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
  table_stats_snapshot_id     UUID PRIMARY KEY,
  dataset_snapshot_id         UUID REFERENCES ops.dataset_snapshots(dataset_snapshot_id)
                              ON DELETE SET NULL,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  schema_name                 TEXT NOT NULL,
  object_name                 TEXT NOT NULL,
  object_kind                 TEXT NOT NULL CHECK (
                              object_kind IN (
                                'table','materialized_view','index','toast','other'
                              )
                            ),
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

CREATE TABLE IF NOT EXISTS ops.pg_stat_statements_snapshots (
  pg_stat_snapshot_id         UUID PRIMARY KEY,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  rank                        INTEGER NOT NULL CHECK (rank >= 1),
  queryid                     TEXT,
  query_fingerprint           TEXT NOT NULL CHECK (
                                char_length(query_fingerprint) BETWEEN 1 AND 64
                              ),
  operation                   TEXT NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 32),
  calls                       BIGINT NOT NULL CHECK (calls >= 0),
  total_exec_time_ms          DOUBLE PRECISION NOT NULL CHECK (total_exec_time_ms >= 0),
  mean_exec_time_ms           DOUBLE PRECISION NOT NULL CHECK (mean_exec_time_ms >= 0),
  max_exec_time_ms            DOUBLE PRECISION NOT NULL CHECK (max_exec_time_ms >= 0),
  rows_returned               BIGINT NOT NULL CHECK (rows_returned >= 0),
  shared_blks_hit             BIGINT NOT NULL DEFAULT 0 CHECK (shared_blks_hit >= 0),
  shared_blks_read            BIGINT NOT NULL DEFAULT 0 CHECK (shared_blks_read >= 0),
  temp_blks_read              BIGINT NOT NULL DEFAULT 0 CHECK (temp_blks_read >= 0),
  temp_blks_written           BIGINT NOT NULL DEFAULT 0 CHECK (temp_blks_written >= 0),
  query_preview               TEXT NOT NULL CHECK (
                                char_length(query_preview) BETWEEN 1 AND 500
                              ),
  stats                       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.slow_observability_samples (
  slow_sample_id              UUID PRIMARY KEY,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_type                 TEXT NOT NULL CHECK (
                                sample_type IN ('api_request','db_query','overload')
                              ),
  method                      TEXT,
  route                       TEXT,
  status_code                 INTEGER,
  elapsed_ms                  DOUBLE PRECISION NOT NULL CHECK (elapsed_ms >= 0),
  threshold_ms                INTEGER CHECK (threshold_ms IS NULL OR threshold_ms >= 0),
  sample_rate                 DOUBLE PRECISION NOT NULL CHECK (
                                sample_rate >= 0 AND sample_rate <= 1
                              ),
  operation                   TEXT CHECK (
                                operation IS NULL
                                OR char_length(operation) BETWEEN 1 AND 32
                              ),
  query_fingerprint           TEXT CHECK (
                                query_fingerprint IS NULL
                                OR char_length(query_fingerprint) BETWEEN 1 AND 64
                              ),
  query_preview               TEXT CHECK (
                                query_preview IS NULL
                                OR char_length(query_preview) BETWEEN 1 AND 500
                              ),
  plan                        JSONB NOT NULL DEFAULT '{}'::jsonb,
  context                     JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.source_file_groups (
  source_file_group_id  UUID PRIMARY KEY,
  category              TEXT NOT NULL,
  group_kind            TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  user_yyyymm           TEXT NOT NULL,
  inferred_yyyymm       TEXT,
  inferred_yyyymm_basis TEXT,
  yyyymm_mismatch       BOOLEAN NOT NULL DEFAULT false,
  expected_file_count   INTEGER NOT NULL DEFAULT 1 CHECK (expected_file_count >= 1),
  actual_file_count     INTEGER NOT NULL DEFAULT 0 CHECK (actual_file_count >= 0),
  coverage              JSONB NOT NULL DEFAULT '{}'::jsonb,
  group_sha256          TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_file_groups_group_kind
    CHECK (group_kind IN ('single_file', 'multi_part')),
  CONSTRAINT chk_ops_source_file_groups_user_yyyymm
    CHECK (user_yyyymm ~ '^\\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_inferred_yyyymm
    CHECK (inferred_yyyymm IS NULL OR inferred_yyyymm ~ '^\\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_group_sha256
    CHECK (group_sha256 IS NULL OR char_length(group_sha256) = 64),
  CONSTRAINT chk_ops_source_file_groups_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_file_groups_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  )),
  CONSTRAINT chk_ops_source_file_groups_available_validation
    CHECK (state <> 'available' OR validation_state IN ('passed','warning'))
);

CREATE TABLE IF NOT EXISTS ops.source_files (
  source_file_id        UUID PRIMARY KEY,
  source_file_group_id  UUID NOT NULL
    REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  original_filename     TEXT NOT NULL,
  part_kind             TEXT NOT NULL DEFAULT 'single',
  part_key              TEXT NOT NULL DEFAULT 'archive',
  part_label            TEXT,
  file_role             TEXT,
  content_type          TEXT,
  compression_format    TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  size_bytes            BIGINT NOT NULL CHECK (size_bytes >= 0),
  sha256                TEXT NOT NULL,
  duplicate_of_file_id  UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  storage_kind          TEXT NOT NULL,
  storage_uri           TEXT NOT NULL,
  bucket                TEXT,
  object_key            TEXT,
  object_etag           TEXT,
  object_version_id     TEXT,
  last_verified_etag    TEXT,
  last_verified_size_bytes BIGINT,
  last_verified_at      TIMESTAMPTZ,
  last_deep_verified_at TIMESTAMPTZ,
  rustfs_endpoint_hash  TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_files_part_kind
    CHECK (part_kind IN ('single', 'sido', 'grid_layer', 'custom')),
  CONSTRAINT chk_ops_source_files_sha256
    CHECK (char_length(sha256) = 64),
  CONSTRAINT chk_ops_source_files_last_verified_size
    CHECK (last_verified_size_bytes IS NULL OR last_verified_size_bytes >= 0),
  CONSTRAINT chk_ops_source_files_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_files_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  )),
  CONSTRAINT chk_ops_source_files_available_validation
    CHECK (state <> 'available' OR validation_state IN ('passed','warning'))
);

CREATE TABLE IF NOT EXISTS ops.source_file_members (
  source_file_member_id UUID PRIMARY KEY,
  source_file_id     UUID NOT NULL REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  member_path        TEXT NOT NULL,
  member_kind        TEXT NOT NULL,
  part_kind          TEXT,
  part_key           TEXT,
  part_label         TEXT,
  layer_name         TEXT,
  geometry_type      TEXT,
  record_count       BIGINT,
  size_bytes         BIGINT,
  sha256             TEXT,
  dbf_fields         JSONB,
  detected_yyyymm    TEXT,
  validation_notes   JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.source_file_validations (
  source_file_validation_id UUID PRIMARY KEY,
  source_file_group_id UUID NOT NULL
    REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  scope               TEXT NOT NULL CHECK (scope IN ('group', 'file')),
  validator_version   TEXT NOT NULL,
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  stage               TEXT,
  progress            DOUBLE PRECISION NOT NULL DEFAULT 0,
  error_code          TEXT,
  error_message       TEXT,
  log_tail            TEXT,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (
    (scope = 'group' AND source_file_id IS NULL)
    OR (scope = 'file' AND source_file_id IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS ops.source_upload_sessions (
  source_upload_session_id TEXT PRIMARY KEY,
  source_file_group_id     UUID NOT NULL,
  category                 TEXT NOT NULL,
  group_kind               TEXT NOT NULL,
  user_yyyymm              TEXT NOT NULL,
  display_name             TEXT NOT NULL,
  state                    TEXT NOT NULL,
  expected_file_count      INTEGER NOT NULL CHECK (expected_file_count >= 1),
  uploaded_file_count      INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_file_count >= 0),
  upload_strategy          TEXT NOT NULL CHECK (upload_strategy IN ('multipart')),
  storage_kind             TEXT NOT NULL,
  bucket                   TEXT,
  prefix                   TEXT,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at               TIMESTAMPTZ,
  registration_deadline_at TIMESTAMPTZ,
  completed_at             TIMESTAMPTZ,
  registered_at            TIMESTAMPTZ,
  error_message            TEXT,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_upload_sessions_user_yyyymm
    CHECK (user_yyyymm ~ '^\\d{6}$')
);

CREATE TABLE IF NOT EXISTS ops.source_upload_session_parts (
  source_upload_session_id TEXT NOT NULL
    REFERENCES ops.source_upload_sessions(source_upload_session_id) ON DELETE CASCADE,
  part_key                 TEXT NOT NULL,
  multipart_upload_id      TEXT,
  part_number              INTEGER NOT NULL CHECK (part_number >= 1),
  part_etag                TEXT,
  part_sha256              TEXT CHECK (part_sha256 IS NULL OR char_length(part_sha256) = 64),
  received_bytes           BIGINT NOT NULL DEFAULT 0 CHECK (received_bytes >= 0),
  completed_at             TIMESTAMPTZ,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (source_upload_session_id, part_key, part_number)
);

CREATE TABLE IF NOT EXISTS ops.source_match_sets (
  source_match_set_id      UUID PRIMARY KEY,
  name                     TEXT NOT NULL,
  description              TEXT,
  profile                  TEXT NOT NULL,
  state                    TEXT NOT NULL,
  source_set_hash          TEXT,
  mixed_yyyymm             BOOLEAN NOT NULL DEFAULT false,
  yyyymm_by_category       JSONB NOT NULL DEFAULT '{}'::jsonb,
  omitted_optional         JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at             TIMESTAMPTZ,
  last_load_job_id         TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  last_consistency_report_id TEXT REFERENCES load_consistency_reports(report_id) ON DELETE SET NULL,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  integrity_alert          BOOLEAN NOT NULL DEFAULT false,
  integrity_alert_at       TIMESTAMPTZ,
  integrity_alert_detail   JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_sets_state
    CHECK (state IN (
      'draft', 'validated', 'active', 'retired',
      'invalid', 'revalidatable', 'restored_from_backup'
    )),
  CONSTRAINT chk_ops_source_match_sets_source_set_hash
    CHECK (
      (state = 'draft' AND source_set_hash IS NULL)
      OR (
        state = 'restored_from_backup'
        AND (source_set_hash IS NULL OR char_length(source_set_hash) = 64)
      )
      OR (
        state NOT IN ('draft', 'restored_from_backup')
        AND source_set_hash IS NOT NULL
        AND char_length(source_set_hash) = 64
      )
    )
);

-- Idempotent FK add (Postgres has no ADD CONSTRAINT IF NOT EXISTS): guarding this lets
-- `ktgctl init-db` re-run against an already-initialized DB to apply newer schema (the rest
-- of SCHEMA_SQL is already idempotent via CREATE ... IF NOT EXISTS / DROP ... IF EXISTS).
DO $$ BEGIN
  ALTER TABLE ops.dataset_snapshots
    ADD CONSTRAINT fk_ops_dataset_snapshots_source_match_set
    FOREIGN KEY (source_match_set_id)
    REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS ops.source_match_set_items (
  source_match_set_item_id UUID PRIMARY KEY,
  source_match_set_id      UUID NOT NULL
    REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE CASCADE,
  category                 TEXT NOT NULL,
  role                     TEXT NOT NULL,
  source_file_group_id     UUID
    REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  required                 BOOLEAN NOT NULL DEFAULT false,
  omitted                  BOOLEAN NOT NULL DEFAULT false,
  omitted_reason           TEXT,
  effective_yyyymm         TEXT,
  validation_enabled       BOOLEAN NOT NULL DEFAULT true,
  load_order               INTEGER,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_set_items_role
    CHECK (role IN (
      'build_required', 'build_recommended',
      'validation_optional', 'enrichment_candidate'
    )),
  CONSTRAINT chk_ops_source_match_set_items_omitted
    CHECK (
    (omitted = false AND source_file_group_id IS NOT NULL)
    OR (omitted = true AND source_file_group_id IS NULL)
  ),
  UNIQUE (source_match_set_id, category)
);

CREATE TABLE IF NOT EXISTS ops.source_storage_reconcile_runs (
  source_storage_reconcile_run_id UUID PRIMARY KEY,
  prefix              TEXT NOT NULL,
  mode                TEXT NOT NULL DEFAULT 'quick' CHECK (mode IN ('quick', 'deep')),
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  scanned_objects     BIGINT NOT NULL DEFAULT 0,
  scanned_db_files    BIGINT NOT NULL DEFAULT 0,
  rehashed_objects    BIGINT NOT NULL DEFAULT 0,
  skipped_rehash_objects BIGINT NOT NULL DEFAULT 0,
  cursor              JSONB NOT NULL DEFAULT '{}'::jsonb,
  mismatch_count      BIGINT NOT NULL DEFAULT 0,
  resolved_count      BIGINT NOT NULL DEFAULT 0,
  log_tail            TEXT,
  summary             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.source_storage_reconcile_items (
  source_storage_reconcile_item_id UUID PRIMARY KEY,
  source_storage_reconcile_run_id UUID NOT NULL
    REFERENCES ops.source_storage_reconcile_runs(source_storage_reconcile_run_id)
    ON DELETE CASCADE,
  issue_type          TEXT NOT NULL,
  source_file_group_id UUID
    REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE SET NULL,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  object_key          TEXT,
  db_sha256           TEXT,
  object_sha256       TEXT,
  db_size_bytes       BIGINT,
  object_size_bytes   BIGINT,
  db_etag             TEXT,
  object_etag         TEXT,
  severity            TEXT NOT NULL,
  state               TEXT NOT NULL DEFAULT 'open',
  resolution_action   TEXT,
  resolved_by         TEXT,
  resolved_at         TIMESTAMPTZ,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.consistency_case_definitions (
  consistency_case_code TEXT PRIMARY KEY CHECK (consistency_case_code ~ '^C\\d+$'),
  display_order         INTEGER NOT NULL,
  name                  TEXT NOT NULL,
  compares              TEXT NOT NULL,
  abnormal_criteria     TEXT NOT NULL,
  evidence              JSONB NOT NULL DEFAULT '[]'::jsonb,
  likely_causes         JSONB NOT NULL DEFAULT '[]'::jsonb,
  decision_guide        TEXT NOT NULL,
  threshold             TEXT,
  default_severity      TEXT,
  state                 TEXT NOT NULL CHECK (state IN ('enabled', 'disabled', 'retired')),
  skip_policy           JSONB NOT NULL DEFAULT '{}'::jsonb,
  sample_schema         JSONB NOT NULL DEFAULT '{}'::jsonb,
  introduced_by         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.consistency_case_inputs (
  consistency_case_code TEXT NOT NULL
    REFERENCES ops.consistency_case_definitions(consistency_case_code) ON DELETE RESTRICT,
  category              TEXT NOT NULL,
  required              BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (consistency_case_code, category)
);

-- Keep in sync with alembic 0022_public_api_keys (fresh init-db must not drift from head).
CREATE TABLE IF NOT EXISTS ops.public_api_keys (
  public_api_key_id UUID PRIMARY KEY,
  key_hash          TEXT NOT NULL UNIQUE CHECK (key_hash ~ '^[0-9a-f]{64}$'),
  key_hint          TEXT NOT NULL CHECK (char_length(key_hint) BETWEEN 6 AND 12),
  label             TEXT CHECK (label IS NULL OR char_length(label) BETWEEN 1 AND 80),
  state             TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','revoked')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT,
  revoked_at        TIMESTAMPTZ,
  revoked_by        TEXT,
  CHECK (
    (state = 'active' AND revoked_at IS NULL AND revoked_by IS NULL)
    OR (state = 'revoked' AND revoked_at IS NOT NULL)
  )
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
CREATE INDEX IF NOT EXISTS idx_juso_text_resolve
  ON tl_juso_text (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no);

CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_pnu
  ON tl_juso_parcel_link (pnu);
CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_road
  ON tl_juso_parcel_link (rncode_full, buld_se_cd, buld_mnnm, buld_slno);
CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_bjd
  ON tl_juso_parcel_link (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);

CREATE INDEX IF NOT EXISTS idx_locsum_geom
  ON tl_locsum_entrc USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_locsum_bd
  ON tl_locsum_entrc (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_locsum_rep
  ON tl_locsum_entrc (bd_mgt_sn, ent_se_cd, ent_man_no) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_locsum_resolve
  ON tl_locsum_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no);

CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_geom
  ON tl_roadaddr_entrc USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_bd
  ON tl_roadaddr_entrc (bd_mgt_sn, ent_man_no);
CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_road
  ON tl_roadaddr_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd);

CREATE INDEX IF NOT EXISTS idx_navi_centroid_geom
  ON tl_navi_buld_centroid USING GIST (centroid_5179);
CREATE INDEX IF NOT EXISTS idx_navi_centroid_resolve
  ON tl_navi_buld_centroid (
    rncode_full, buld_se_cd, buld_mnnm, buld_slno, (left(bjd_cd, 8))
  );
CREATE INDEX IF NOT EXISTS idx_navi_centroid_sigungu_buld_nm_trgm
  ON tl_navi_buld_centroid USING GIN (sigungu_buld_nm_nrm gin_trgm_ops)
  WHERE sigungu_buld_nm_nrm IS NOT NULL AND sigungu_buld_nm_nrm <> '';
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
CREATE INDEX IF NOT EXISTS idx_region_radius_parts_geom
  ON region_radius_parts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_region_radius_parts_level_parent_sido
  ON region_radius_parts (level, parent_sido_cd);
CREATE INDEX IF NOT EXISTS idx_region_radius_parts_level_parent_sig
  ON region_radius_parts (level, parent_sig_cd);
CREATE INDEX IF NOT EXISTS idx_kodis_bas_geom ON tl_kodis_bas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_kodis_bas_id ON tl_kodis_bas (bas_id);
CREATE INDEX IF NOT EXISTS idx_sppn_makarea_geom ON tl_sppn_makarea USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sppn_makarea_sig ON tl_sppn_makarea (sig_cd);
CREATE INDEX IF NOT EXISTS idx_spbd_buld_polygon_geom ON tl_spbd_buld_polygon USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_spbd_buld_polygon_resolve
  ON tl_spbd_buld_polygon (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd);
CREATE INDEX IF NOT EXISTS idx_sprd_manage_geom ON tl_sprd_manage USING GIST (geom);
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
-- Reconciler / startup-recovery hot path: only executor='dagster' running jobs need a
-- Dagster-run liveness/lease check, and they are a tiny minority of rows. A partial
-- index on the lease keeps that scan cheap and lets the reconciler order/filter by
-- lease_expires_at without touching the api_in_process majority (T-290c, ADR-066 §5).
CREATE INDEX IF NOT EXISTS idx_load_jobs_dagster_running
  ON load_jobs (lease_expires_at)
  WHERE executor = 'dagster' AND state = 'running';
-- Reverse split-brain scan: the app already marked a Dagster-backed job terminal, but
-- the Dagster run may still be alive and must be terminated by the reconciler.
CREATE INDEX IF NOT EXISTS idx_load_jobs_dagster_terminal_orphan
  ON load_jobs (created_at)
  WHERE executor = 'dagster'
    AND state IN ('failed','cancelled')
    AND orchestrator_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_consistency_started
  ON load_consistency_reports (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_geo_cache_expires
  ON geo_cache (expires_at);

CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_report
  ON ops.consistency_case_samples (report_id, case_code, severity, decision_state);
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_case_severity
  ON ops.consistency_case_samples (case_code, severity, distance_m DESC);
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_sig
  ON ops.consistency_case_samples (sig_cd, case_code);
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_review
  ON ops.consistency_case_samples (report_id, case_code, decision_state, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_4326
  ON ops.consistency_case_samples USING GIST (point_4326);

CREATE INDEX IF NOT EXISTS idx_ops_audit_events_occurred
  ON ops.audit_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_audit_events_action
  ON ops.audit_events (action, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_dataset_snapshots_created
  ON ops.dataset_snapshots (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_serving_releases_created
  ON ops.serving_releases (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_serving_releases_one_active
  ON ops.serving_releases (state) WHERE state = 'active';
CREATE INDEX IF NOT EXISTS idx_ops_artifacts_type_created
  ON ops.artifacts (artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_maintenance_windows_active
  ON ops.maintenance_windows (kind, state, starts_at)
  WHERE state IN ('scheduled','active','ending');
CREATE INDEX IF NOT EXISTS idx_ops_table_stats_snapshots_captured
  ON ops.table_stats_snapshots (captured_at DESC, schema_name, object_name);
CREATE INDEX IF NOT EXISTS idx_ops_pg_stat_statements_snapshots_captured
  ON ops.pg_stat_statements_snapshots (captured_at DESC, rank);
CREATE INDEX IF NOT EXISTS idx_ops_pg_stat_statements_snapshots_fingerprint
  ON ops.pg_stat_statements_snapshots (query_fingerprint, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_captured
  ON ops.slow_observability_samples (captured_at DESC, sample_type);
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_route
  ON ops.slow_observability_samples (route, captured_at DESC)
  WHERE route IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_query
  ON ops.slow_observability_samples (query_fingerprint, captured_at DESC)
  WHERE query_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_source_match_sets_one_active
  ON ops.source_match_sets (state) WHERE state = 'active';
CREATE INDEX IF NOT EXISTS idx_ops_source_file_groups_category_state
  ON ops.source_file_groups (category, state);
CREATE INDEX IF NOT EXISTS idx_ops_source_files_group
  ON ops.source_files (source_file_group_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_source_files_object
  ON ops.source_files (bucket, object_key)
  WHERE bucket IS NOT NULL AND object_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ops_source_file_members_file
  ON ops.source_file_members (source_file_id);
CREATE INDEX IF NOT EXISTS idx_ops_source_file_validations_group
  ON ops.source_file_validations (source_file_group_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_source_upload_sessions_category
  ON ops.source_upload_sessions (category, user_yyyymm, state);
CREATE INDEX IF NOT EXISTS idx_ops_source_storage_reconcile_items_run
  ON ops.source_storage_reconcile_items (source_storage_reconcile_run_id, issue_type);
CREATE INDEX IF NOT EXISTS idx_ops_source_match_set_items_group
  ON ops.source_match_set_items (source_file_group_id) WHERE source_file_group_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_definitions_order
  ON ops.consistency_case_definitions (display_order);
CREATE INDEX IF NOT EXISTS idx_ops_dataset_snapshots_source_match_set_id
  ON ops.dataset_snapshots (source_match_set_id) WHERE source_match_set_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ops_public_api_keys_active_hash
  ON ops.public_api_keys (key_hash)
  WHERE state = 'active';
CREATE INDEX IF NOT EXISTS idx_ops_public_api_keys_created_at
  ON ops.public_api_keys (created_at DESC);
"""

REGION_RADIUS_PARTS_REFRESH_SQL = """
SET search_path = public, x_extension;

CREATE TABLE IF NOT EXISTS region_radius_parts (
  level           TEXT NOT NULL CHECK (level IN ('sido','sigungu','emd')),
  code            TEXT NOT NULL,
  name            TEXT,
  parent_sido_cd  TEXT,
  parent_sig_cd   TEXT,
  part_no         INTEGER NOT NULL,
  geom            geometry(Geometry, 5179) NOT NULL,
  refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (level, code, part_no)
);

CREATE INDEX IF NOT EXISTS idx_region_radius_parts_geom
  ON region_radius_parts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_region_radius_parts_level_parent_sido
  ON region_radius_parts (level, parent_sido_cd);
CREATE INDEX IF NOT EXISTS idx_region_radius_parts_level_parent_sig
  ON region_radius_parts (level, parent_sig_cd);

TRUNCATE TABLE region_radius_parts;

WITH source_regions AS (
  SELECT 'sido'::text AS level,
         c.ctprvn_cd AS code,
         c.ctp_kor_nm AS name,
         c.ctprvn_cd AS parent_sido_cd,
         NULL::text AS parent_sig_cd,
         c.geom
    FROM tl_scco_ctprvn c
   WHERE c.geom IS NOT NULL
     AND NOT ST_IsEmpty(c.geom)
  UNION ALL
  SELECT 'sigungu'::text AS level,
         s.sig_cd AS code,
         s.sig_kor_nm AS name,
         left(s.sig_cd, 2) AS parent_sido_cd,
         s.sig_cd AS parent_sig_cd,
         s.geom
    FROM tl_scco_sig s
   WHERE s.geom IS NOT NULL
     AND NOT ST_IsEmpty(s.geom)
  UNION ALL
  SELECT 'emd'::text AS level,
         e.emd_cd AS code,
         e.emd_kor_nm AS name,
         left(e.emd_cd, 2) AS parent_sido_cd,
         left(e.emd_cd, 5) AS parent_sig_cd,
         e.geom
    FROM tl_scco_emd e
   WHERE e.geom IS NOT NULL
     AND NOT ST_IsEmpty(e.geom)
),
subdivided AS (
  SELECT s.level,
         s.code,
         s.name,
         s.parent_sido_cd,
         s.parent_sig_cd,
         row_number() OVER (
           PARTITION BY s.level, s.code
           ORDER BY ST_Area(part.geom) DESC
         )::integer AS part_no,
         part.geom
    FROM source_regions s
    CROSS JOIN LATERAL ST_Subdivide(s.geom, 256) AS part(geom)
)
INSERT INTO region_radius_parts (
  level, code, name, parent_sido_cd, parent_sig_cd, part_no, geom
)
SELECT level, code, name, parent_sido_cd, parent_sig_cd, part_no, geom
  FROM subdivided;

ANALYZE region_radius_parts;
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
    FROM (
      SELECT bd_mgt_sn,
             ent_man_no,
             geom,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn,
            source_priority,
            rep_priority,
            ent_man_no NULLS LAST
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
         centroid_5179,
         sigungu_buld_nm,
         sigungu_buld_nm_nrm
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
  NULLIF(nc.sigungu_buld_nm, '') AS sigungu_buld_nm,
  NULLIF(nc.sigungu_buld_nm_nrm, '') AS sigungu_buld_nm_nrm,
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
CREATE INDEX idx_mv_jibun_name_exact
  ON mv_geocode_target (
    si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno,
    emd_nm, li_nm, pt_source, bd_mgt_sn
  );
CREATE INDEX idx_mv_rn_nrm_exact
  ON mv_geocode_target (rn_nrm, bd_mgt_sn);
CREATE INDEX idx_mv_buld_nm_nrm_exact
  ON mv_geocode_target (buld_nm_nrm, bd_mgt_sn) WHERE buld_nm_nrm IS NOT NULL;
CREATE INDEX idx_mv_sigungu_buld_nm_nrm_exact
  ON mv_geocode_target (sigungu_buld_nm_nrm, bd_mgt_sn)
  WHERE sigungu_buld_nm_nrm IS NOT NULL;
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

TEXT_SEARCH_MV_SQL = """
SET search_path = public, x_extension;

DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search;
CREATE MATERIALIZED VIEW mv_geocode_text_search AS
SELECT
  bd_mgt_sn,
  left(bjd_cd, 2) AS sido_cd,
  left(bjd_cd, 5) AS sig_cd,
  bjd_cd,
  si_nm,
  sgg_nm,
  rn_nrm,
  buld_nm_nrm,
  sigungu_buld_nm_nrm,
  buld_mnnm,
  buld_slno,
  buld_se_cd,
  pt_source
FROM mv_geocode_target
WHERE rn_nrm IS NOT NULL
  AND rn_nrm <> ''
WITH DATA;

CREATE UNIQUE INDEX idx_mv_text_search_pk
  ON mv_geocode_text_search (bd_mgt_sn);
CREATE INDEX idx_mv_text_search_sig_buld
  ON mv_geocode_text_search (sig_cd, buld_mnnm, buld_slno, buld_se_cd, bd_mgt_sn);
CREATE INDEX idx_mv_text_search_sido_buld
  ON mv_geocode_text_search (sido_cd, buld_mnnm, buld_slno, buld_se_cd, bd_mgt_sn);
CREATE INDEX idx_mv_text_search_bjd_prefix_buld
  ON mv_geocode_text_search (
    bjd_cd text_pattern_ops, buld_mnnm, buld_slno, buld_se_cd, bd_mgt_sn
  );
CREATE INDEX idx_mv_text_search_rn_trgm
  ON mv_geocode_text_search USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX idx_mv_text_search_buld_nm_trgm
  ON mv_geocode_text_search USING GIN (buld_nm_nrm gin_trgm_ops)
  WHERE buld_nm_nrm IS NOT NULL;
CREATE INDEX idx_mv_text_search_sigungu_buld_nm_trgm
  ON mv_geocode_text_search USING GIN (sigungu_buld_nm_nrm gin_trgm_ops)
  WHERE sigungu_buld_nm_nrm IS NOT NULL;
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
    """Return non-empty SQL statements while preserving quoted semicolons."""

    statements: list[str] = []
    start = 0
    index = 0
    quote: str | None = None
    dollar_tag: str | None = None
    line_comment = False
    block_comment = False

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue

        if dollar_tag is not None:
            if sql.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
                continue
            index += 1
            continue

        if quote is not None:
            if char == quote:
                if quote == "'" and next_char == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char == "-" and next_char == "-":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if match is not None:
                dollar_tag = match.group(0)
                index += len(dollar_tag)
                continue
        if char == ";":
            statement = sql[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1

    statement = sql[start:].strip()
    if statement:
        statements.append(statement)
    return tuple(statements)
