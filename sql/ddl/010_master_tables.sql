CREATE TABLE IF NOT EXISTS tl_scco_ctprvn (
  ctprvn_cd TEXT PRIMARY KEY,
  ctp_eng_nm TEXT,
  ctp_kor_nm TEXT NOT NULL,
  geom geometry(MULTIPOLYGON, 5179)
);

CREATE TABLE IF NOT EXISTS tl_scco_sig (
  sig_cd TEXT PRIMARY KEY,
  sig_eng_nm TEXT,
  sig_kor_nm TEXT NOT NULL,
  sig_nm_nrm TEXT GENERATED ALWAYS AS (regexp_replace(sig_kor_nm, '\s+', '', 'g')) STORED,
  geom geometry(MULTIPOLYGON, 5179)
);

CREATE TABLE IF NOT EXISTS tl_scco_emd (
  emd_cd TEXT PRIMARY KEY,
  emd_eng_nm TEXT,
  emd_kor_nm TEXT NOT NULL,
  sig_cd TEXT GENERATED ALWAYS AS (substr(emd_cd, 1, 5)) STORED,
  geom geometry(MULTIPOLYGON, 5179)
);

CREATE TABLE IF NOT EXISTS tl_scco_li (
  li_cd TEXT PRIMARY KEY,
  li_eng_nm TEXT,
  li_kor_nm TEXT NOT NULL,
  emd_cd_8 TEXT GENERATED ALWAYS AS (substr(li_cd, 1, 8)) STORED,
  geom geometry(MULTIPOLYGON, 5179)
);

CREATE TABLE IF NOT EXISTS tl_kodis_bas (
  bas_mgt_sn TEXT PRIMARY KEY,
  bas_id TEXT NOT NULL,
  bas_ar NUMERIC,
  ctp_kor_nm TEXT,
  sig_cd TEXT,
  sig_kor_nm TEXT,
  mvmn_de TEXT,
  mvmn_resn TEXT,
  ntfc_de TEXT,
  opert_de TEXT,
  geom geometry(MULTIPOLYGON, 5179)
);

CREATE TABLE IF NOT EXISTS tl_sprd_manage (
  sig_cd TEXT NOT NULL,
  rds_man_no BIGINT NOT NULL,
  rn_cd TEXT NOT NULL,
  rn TEXT NOT NULL,
  rn_nrm TEXT GENERATED ALWAYS AS (regexp_replace(rn, '\s+', '', 'g')) STORED,
  rncode_full TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  eng_rn TEXT,
  bsi_int TEXT,
  rds_dpn_se TEXT,
  rbp_cn TEXT,
  rep_cn TEXT,
  road_bt NUMERIC,
  road_lt NUMERIC,
  roa_cls_se TEXT,
  wdr_rd_cd TEXT,
  alwnc_de TEXT,
  alwnc_resn TEXT,
  mvmn_de TEXT,
  mvmn_resn TEXT,
  mvm_res_cd TEXT,
  ntfc_de TEXT,
  opert_de TEXT,
  PRIMARY KEY (sig_cd, rds_man_no)
);

CREATE TABLE IF NOT EXISTS tl_sprd_intrvl (
  sig_cd TEXT NOT NULL,
  rds_man_no BIGINT NOT NULL,
  bsi_int_sn BIGINT NOT NULL,
  odd_bsi_mn INTEGER,
  odd_bsi_sl INTEGER,
  eve_bsi_mn INTEGER,
  eve_bsi_sl INTEGER,
  opert_de TEXT,
  PRIMARY KEY (sig_cd, rds_man_no, bsi_int_sn)
);

CREATE TABLE IF NOT EXISTS tl_sprd_rw (
  sig_cd TEXT NOT NULL,
  rw_sn BIGINT NOT NULL,
  opert_de TEXT,
  geom geometry(MULTILINESTRING, 5179),
  PRIMARY KEY (sig_cd, rw_sn)
);

CREATE TABLE IF NOT EXISTS tl_spbd_eqb (
  sig_cd TEXT NOT NULL,
  eqb_man_sn BIGINT NOT NULL,
  opert_de TEXT,
  PRIMARY KEY (sig_cd, eqb_man_sn)
);

CREATE TABLE IF NOT EXISTS tl_spbd_buld (
  sig_cd TEXT NOT NULL,
  bul_man_no BIGINT NOT NULL,
  bd_mgt_sn TEXT NOT NULL UNIQUE,
  rn_cd TEXT NOT NULL,
  rds_sig_cd TEXT,
  rds_man_no BIGINT,
  bsi_int_sn BIGINT,
  bsi_zon_no TEXT,
  buld_mnnm INTEGER NOT NULL,
  buld_slno INTEGER NOT NULL DEFAULT 0,
  buld_se_cd TEXT,
  buld_nm TEXT,
  buld_nm_dc TEXT,
  buld_nm_nrm TEXT GENERATED ALWAYS AS (regexp_replace(COALESCE(buld_nm, ''), '\s+', '', 'g')) STORED,
  bdtyp_cd TEXT,
  bul_dpn_se TEXT,
  bul_eng_nm TEXT,
  emd_cd TEXT NOT NULL,
  li_cd TEXT,
  bjd_cd TEXT GENERATED ALWAYS AS (sig_cd || emd_cd || COALESCE(NULLIF(li_cd, ''), '00')) STORED,
  rncode_full TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  eqb_man_sn BIGINT,
  gro_flo_co INTEGER,
  und_flo_co INTEGER,
  lnbr_mnnm INTEGER NOT NULL,
  lnbr_slno INTEGER NOT NULL DEFAULT 0,
  mntn_yn TEXT NOT NULL DEFAULT '0' CHECK (mntn_yn IN ('0', '1')),
  pnu TEXT GENERATED ALWAYS AS (
    sig_cd
    || emd_cd
    || COALESCE(NULLIF(li_cd, ''), '00')
    || CASE mntn_yn WHEN '1' THEN '2' ELSE '1' END
    || lpad(lnbr_mnnm::text, 4, '0')
    || lpad(COALESCE(lnbr_slno, 0)::text, 4, '0')
  ) STORED,
  pos_bul_nm TEXT,
  mvmn_de TEXT,
  mvmn_resn TEXT,
  mvm_res_cd TEXT,
  ntfc_de TEXT,
  opert_de TEXT,
  geom geometry(MULTIPOLYGON, 5179),
  PRIMARY KEY (sig_cd, bul_man_no)
);

CREATE TABLE IF NOT EXISTS tl_spbd_entrc (
  sig_cd TEXT NOT NULL,
  ent_man_no BIGINT NOT NULL,
  bul_man_no BIGINT NOT NULL,
  eqb_man_sn BIGINT,
  entrc_se TEXT,
  opert_de TEXT,
  geom geometry(POINT, 5179),
  PRIMARY KEY (sig_cd, ent_man_no)
);
