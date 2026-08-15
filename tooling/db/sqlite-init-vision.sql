PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vision_runs (
  run_id               TEXT PRIMARY KEY,
  created_at           TEXT NOT NULL,
  source_filename      TEXT,
  status               TEXT NOT NULL DEFAULT 'completed',
  segmentation_backend TEXT,
  dino_backend         TEXT,
  used_fallback        INTEGER,
  frames_sampled       INTEGER,
  frames_usable        INTEGER,
  zone_count           INTEGER,
  field_detected       INTEGER,
  total_runtime_sec    REAL,
  stage_latency_json   TEXT,
  results_path         TEXT,
  metrics_json         TEXT,
  report_json          TEXT
);

CREATE INDEX IF NOT EXISTS idx_vision_runs_created ON vision_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', '1');
