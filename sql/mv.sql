CREATE MATERIALIZED VIEW IF NOT EXISTS mv_geocode_target AS
SELECT
  b.bd_mgt_sn,
  b.rncode_full,
  b.buld_mnnm,
  b.buld_slno,
  b.buld_se_cd,
  b.buld_nm,
  b.buld_nm_nrm,
  b.bjd_cd,
  b.pnu,
  b.mntn_yn,
  b.lnbr_mnnm,
  b.lnbr_slno,
  b.bsi_zon_no AS zip_no,
  r.rn AS road_nm,
  s.sig_kor_nm AS sgg_nm,
  c.ctp_kor_nm AS si_nm,
  e.emd_kor_nm AS emd_nm,
  ent.geom AS ent_pt_5179,
  ST_Transform(ent.geom, 4326) AS ent_pt_4326
FROM tl_spbd_buld AS b
LEFT JOIN tl_sprd_manage AS r ON r.rncode_full = b.rncode_full
LEFT JOIN tl_scco_sig AS s ON s.sig_cd = b.sig_cd
LEFT JOIN tl_scco_ctprvn AS c ON c.ctprvn_cd = substr(b.bjd_cd, 1, 2)
LEFT JOIN tl_scco_emd AS e ON e.emd_cd = substr(b.bjd_cd, 1, 8)
LEFT JOIN tl_spbd_entrc AS ent ON ent.sig_cd = b.sig_cd AND ent.bul_man_no = b.bul_man_no
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_geocode_target_pk
  ON mv_geocode_target (bd_mgt_sn);

CREATE INDEX IF NOT EXISTS idx_mv_road
  ON mv_geocode_target (rncode_full, buld_mnnm, buld_slno, buld_se_cd);

CREATE INDEX IF NOT EXISTS idx_mv_jibun
  ON mv_geocode_target (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);

CREATE INDEX IF NOT EXISTS idx_mv_geom5179
  ON mv_geocode_target USING GIST (ent_pt_5179);

CREATE INDEX IF NOT EXISTS idx_mv_geom4326
  ON mv_geocode_target USING GIST (ent_pt_4326);
