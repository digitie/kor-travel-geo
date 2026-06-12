-- Generated mirror of src/kortravelgeo/infra/sql.py for review/DBA use.

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
  ON mv_geocode_target (si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno, emd_nm, li_nm, pt_source, bd_mgt_sn);
CREATE INDEX idx_mv_rn_nrm_exact
  ON mv_geocode_target (rn_nrm, bd_mgt_sn);
CREATE INDEX idx_mv_buld_nm_nrm_exact
  ON mv_geocode_target (buld_nm_nrm, bd_mgt_sn) WHERE buld_nm_nrm IS NOT NULL;
CREATE INDEX idx_mv_rn_trgm
  ON mv_geocode_target USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX idx_mv_buld_nm_trgm
  ON mv_geocode_target USING GIN (buld_nm_nrm gin_trgm_ops);
CREATE INDEX idx_mv_sigungu_buld_nm_nrm_exact
  ON mv_geocode_target (sigungu_buld_nm_nrm, bd_mgt_sn)
  WHERE sigungu_buld_nm_nrm IS NOT NULL;
CREATE INDEX idx_mv_geom5179
  ON mv_geocode_target USING GIST (pt_5179) WHERE pt_5179 IS NOT NULL;
CREATE INDEX idx_mv_geom4326
  ON mv_geocode_target USING GIST (pt_4326) WHERE pt_4326 IS NOT NULL;
CREATE INDEX idx_mv_pt_source ON mv_geocode_target (pt_source);
