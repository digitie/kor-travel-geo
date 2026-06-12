-- Generated mirror of src/kortravelgeo/infra/sql.py for review/DBA use.

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
