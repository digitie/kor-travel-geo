CREATE TABLE IF NOT EXISTS postal_pobox (
  bd_mgt_sn TEXT PRIMARY KEY,
  zip_no TEXT NOT NULL,
  rn_code TEXT,
  pobox_kind TEXT CHECK (pobox_kind IN ('PO', 'PG')),
  pobox_name TEXT,
  pobox_no_mn INTEGER,
  pobox_no_sl INTEGER DEFAULT 0,
  si_nm TEXT,
  sgg_nm TEXT,
  emd_nm TEXT,
  bjd_cd TEXT,
  loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS postal_bulk_delivery (
  bulk_id BIGSERIAL PRIMARY KEY,
  zip_no TEXT NOT NULL,
  bd_mgt_sn TEXT,
  bulk_name TEXT NOT NULL,
  detail TEXT,
  loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
