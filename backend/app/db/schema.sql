PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS journal_entries (
  id                 TEXT PRIMARY KEY,            -- entry_xxx (server-generated)
  title              TEXT NOT NULL,               -- 'Outdoor note · YYYY-MM-DD'
  created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  image_path         TEXT NOT NULL,               -- relative: uploads/{id}/original.jpg
  thumbnail_path     TEXT NOT NULL,               -- relative: uploads/{id}/thumb_512.jpg
  ai_analysis_json   TEXT,                        -- NULL if saved without AI; else frozen AIAnalysis JSON
  ai_model_id        TEXT,                        -- e.g. 'gemma4:e2b'; NULL iff ai_analysis_json NULL
  ai_analyzed_at     TEXT,                        -- RFC3339 from analysis; NULL iff no AI
  user_notes         TEXT NOT NULL CHECK (length(user_notes) BETWEEN 1 AND 2000),
  experiment_done    INTEGER NOT NULL DEFAULT 0 CHECK (experiment_done IN (0,1)),
  experiment_result  TEXT CHECK (experiment_result IS NULL OR length(experiment_result) <= 2000)
);

CREATE TABLE IF NOT EXISTS ai_analyses (
  id              TEXT PRIMARY KEY,              -- tmp_xxx or ana_xxx
  entry_id        TEXT REFERENCES journal_entries(id) ON DELETE SET NULL,
  model_id        TEXT NOT NULL,
  analyzed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  analysis_json   TEXT NOT NULL,                 -- validated AIAnalysis JSON
  image_tmp_path  TEXT,                          -- relative tmp path; NULL after promotion/cleanup
  saved           INTEGER NOT NULL DEFAULT 0 CHECK (saved IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_entries_created ON journal_entries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_entry ON ai_analyses(entry_id);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
