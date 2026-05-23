CREATE TABLE IF NOT EXISTS load_manifest (
  table_name TEXT PRIMARY KEY,
  last_full_load_at TIMESTAMPTZ,
  last_delta_at TIMESTAMPTZ,
  last_mvmn_de TEXT,
  row_count BIGINT NOT NULL DEFAULT 0,
  source_zip TEXT,
  source_checksum TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS load_jobs (
  job_id UUID PRIMARY KEY,
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
  progress NUMERIC(5,4) NOT NULL DEFAULT 0,
  current_stage TEXT,
  error_message TEXT,
  source_checksum TEXT,
  heartbeat_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS load_codes (
  code TEXT PRIMARY KEY,
  action TEXT NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
  note TEXT
);

INSERT INTO load_codes(code, action) VALUES
  ('31', 'insert'), ('33', 'insert'),
  ('34', 'update'), ('35', 'update'), ('36', 'update'),
  ('63', 'delete'), ('64', 'delete')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS geo_cache (
  cache_key TEXT PRIMARY KEY,
  service TEXT NOT NULL,
  payload JSONB NOT NULL,
  hit_count BIGINT NOT NULL DEFAULT 0,
  last_hit_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
