CREATE INDEX IF NOT EXISTS idx_buld_road_match
  ON tl_spbd_buld (rncode_full, buld_mnnm, buld_slno, buld_se_cd);

CREATE INDEX IF NOT EXISTS idx_buld_jibun_match
  ON tl_spbd_buld (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);

CREATE INDEX IF NOT EXISTS idx_buld_pnu
  ON tl_spbd_buld (pnu);

CREATE INDEX IF NOT EXISTS idx_kodis_bas_geom
  ON tl_kodis_bas USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_entrc_geom
  ON tl_spbd_entrc USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_entrc_main
  ON tl_spbd_entrc (sig_cd, bul_man_no);

CREATE INDEX IF NOT EXISTS idx_sprd_manage_rn_trgm
  ON tl_sprd_manage USING GIN (rn_nrm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_bulk_bd_mgt_sn
  ON postal_bulk_delivery (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_load_jobs_state_created
  ON load_jobs (state, created_at);

CREATE INDEX IF NOT EXISTS idx_geo_cache_expires
  ON geo_cache (expires_at);
