-- Generated mirror of src/kortravelgeo/infra/sql.py for review/DBA use.

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
