# Verdantra — Database (DATABASE.md)

**Version:** 0.1.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP
**Depends on:** `PRD.md` (D4), `ARCHITECTURE.md` §§2/5, `API.md` · **Implements:** persistence for `backend/app/db/schema.sql` + `backend/app/db.py`

## 1. Engine and file layout

- **Engine:** SQLite via Python standard library `sqlite3` (no ORM, no migration tool in MVP — PRD D4). `sqlite3.sqlite_version` must be ≥ 3.35 (JSON1 + DROP COLUMN support); record actual version in the build PR.
- **File:** single database `data/verdantra.db` (default; override `DATABASE_PATH`). Pragmas on every connection: `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;`
- **Concurrency:** single Uvicorn worker (`--workers 1`) in MVP. Writers retry once on `SQLITE_BUSY`, then surface `503 db_busy` (never a 500). Readers never block writers under WAL for this workload.
- **Images on filesystem (not BLOBs):** `data/uploads/{entry_id}/original.{jpg|png|webp}` + `thumb_512.{jpg}`; temp uploads `data/uploads/tmp/{temp_id}.*`. DB stores relative paths only. `data/` contents are git-ignored except `.gitkeep` (see `SECURITY.md` §6).
- **Schema versioning:** `schema_version(version INTEGER PRIMARY KEY, applied_at TEXT)` single row; `schema.sql` is the single source of truth; any change bumps version + appends migration SQL in a `migrations/` note (post-MVP tooling deferred).

## 2. Entity model (maps 1:1 to API.md)

- `journal_entries` — one row per saved entry (the unit users see). Holds user-confirmed fields + denormalized AI snapshot + image paths. AI snapshot is a **frozen JSON copy** of the `API.md` §2 analysis at save time (never a live reference), so later model changes cannot rewrite history.
- `ai_analyses` — optional normalized log of every successful analyze call (including un-saved ones, `entry_id NULL`), enabling the verification log and debugging without PII. Temp rows older than 1 hour are swept.
- No users/accounts table (PRD D3). No sessions, no tags, no locations table in MVP (location deliberately not collected — see §7).

## 3. DDL (copy verbatim into `backend/app/db/schema.sql`)

```sql
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
```

Type notes: booleans as `INTEGER 0/1`; timestamps as RFC 3339 `TEXT` (lexicographically sortable); JSON validated in Python before insert (SQLite JSON1 used only for debugging queries, never as a constraint substitute).

## 4. Transaction scopes (implement exactly)

1. **Save entry** (`POST /api/v1/journal-entries`): `BEGIN IMMEDIATE` → verify `temp_image_id` row in `ai_analyses` (or accept null-AI path) → validate `user_notes`/lengths + `ai_model_id == AI_MODEL_ID` → `mkdir data/uploads/{id}` → move temp file → generate thumbnail (Pillow, longest edge 512, JPEG q80) → `INSERT journal_entries` → `UPDATE ai_analyses SET entry_id, saved=1` → `COMMIT`. On any failure: `ROLLBACK`, remove created files, return the `API.md` §6 error. Order matters: files first, then row, so a crash cannot leave a row pointing at missing files without detection (orphan sweep covers the reverse).
2. **Delete entry** (`DELETE`): `SELECT` paths → `DELETE FROM journal_entries` (analyses keep `entry_id NULL` history) → `COMMIT` → delete `data/uploads/{id}/` tree. If file deletion fails after commit, log `orphan_files` warning; sweep job removes it next run.
3. **Temp sweep** (on each analyze call + startup): `DELETE FROM ai_analyses WHERE saved=0 AND analyzed_at < now-1h` + delete matching `data/uploads/tmp/*` files. No user data affected.

## 5. Seed, backup, restore (MVP-manual, documented)

- **Seed:** none in MVP (empty journal is the correct first-run state). Dev convenience script `backend/app/db.py --init` creates schema + `.gitkeep` only.
- **Backup:** `sqlite3 data/verdantra.db ".backup 'data/backup-YYYYMMDD.db'"` + `rsync -a data/uploads/ <backup-dest>/uploads/`; document in `README.md` runbook. No automated cron in MVP.
- **Restore:** stop app → replace `verdantra.db` + `uploads/` → start → `GET /healthz` (`db: ok`) → spot-check one entry detail. `PRAGMA integrity_check;` must return `ok` before going live.

## 6. Integrity, limits, and honesty

- **No invented data:** no triggers or defaults generate measurements, species names, or coordinates. `title` date is server local date at save; `created_at`/`analyzed_at` are system timestamps, labeled as such in UI.
- **Orphan detection query** (runbook): `SELECT id FROM ai_analyses WHERE saved=0 AND analyzed_at < …` cross-checked against `data/uploads/tmp/` listing; any file without a row is safe to delete.
- **Growth:** single-file SQLite is fine for MVP scale (hundreds of entries, ~2–5 MB images each). Document the ceiling in code comment: migrate to Postgres + object storage only post-MVP if `verdantra.db` exceeds 2 GB or concurrent writers are needed.
- **EXIF/GPS:** GPS tags are stripped at upload (`SECURITY.md` §4); no lat/long columns exist — this is intentional. Adding location is a privacy-reviewed future decision, not a silent schema addition.

## 7. Acceptance

- [ ] `schema.sql` executes cleanly on a fresh checkout (`sqlite3 data/verdantra.db < backend/app/db/schema.sql`; `integrity_check → ok`).
- [ ] Save → detail → delete round-trip leaves no orphan rows or files (verify with orphan query + `ls data/uploads/`).
- [ ] `ai_analysis_json` stored is byte-identical to the analysis returned at analyze time (frozen snapshot property).
- [ ] Forced `SQLITE_BUSY` (two rapid saves) surfaces at most one retried success or honest `503 db_busy` — never a 500 with a traceback.

*Next: `SECURITY.md` for validation, privacy, and secrets handling around this store.*
