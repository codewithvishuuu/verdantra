# Verdantra — Architecture (ARCHITECTURE.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP (hosted time-box re-baseline for M1–M5)
**Depends on:** `PRD.md`, `DESIGN.md` · **Feeds:** `API.md`, `DATABASE.md`, `AI_SYSTEM.md`, `IMPLEMENTATION_PLAN.md`

## 1. System overview

Single-tenant, two-tier web app (no login, single device — PRD decision D3):

```
Browser (React SPA) ──HTTPS/JSON+multipart──▶ FastAPI (Uvicorn) ──▶ SQLite file (WAL)
                                                    │
                                                    └─▶ AIService ─┬─▶ Gemini API (hosted, `gemma-4-26b-a4b-it`) [AI_PROVIDER=gemini, default]
                                                                     ├─▶ Ollama (local, `gemma4:e2b`) [AI_PROVIDER=ollama; live image verification pending]
                                                                     └─▶ Auto: hosted first, one local fallback on transport failure [AI_PROVIDER=auto; live fallback unverified]
```

- **Frontend** `frontend/`: React 18+ / TypeScript 5+ / Vite 5+ / Tailwind 3.4+, served as static files (dev: `vite dev` proxy; prod: built `dist/` served by the same Droplet behind a reverse proxy or static host — see §6).
- **Backend** `backend/`: Python 3.11+ / FastAPI 0.115+ / Uvicorn, sync `sqlite3` stdlib access via a small repository layer (no ORM in MVP — PRD D4).
- **Data:** one SQLite file `data/verdantra.db` + image files `data/uploads/{entry_id}/original.*` + `thumb_512.*`. No external DB, queue, cache, or object storage in MVP.
- **AI:** strict adapter interface so the verified Gemma 4 path can be swapped without touching routes (see `AI_SYSTEM.md` §3). No background workers in MVP — analyze is a synchronous request with a 150s server timeout (provisional pending the five-run log).

## 2. Practical project structure (create exactly this in Milestone 1)

```
verdantra/
  PRD.md  DESIGN.md  ARCHITECTURE.md  AI_SYSTEM.md  USER_FLOWS.md
  API.md  DATABASE.md  SECURITY.md  IMPLEMENTATION_PLAN.md  README.md
  .gitignore  .env.example
  assets/logo/verdantra-logo.svg   # provided file, verbatim (missing at doc time — see PRD §9)
  frontend/
    package.json  vite.config.ts  tailwind.config.js  postcss.config.js  tsconfig.json
    index.html  public/favicon-32.png
    src/main.tsx  src/App.tsx  src/index.css
    src/lib/api.ts                 # typed fetch client matching API.md
    src/components/ (Header, Badges, UploadCard, AIPanel, ObservationForm, EntryCard, ErrorCard)
    src/pages/ (NewObservation, JournalList, EntryDetail)
  backend/
    requirements.txt               # fastapi, uvicorn, python-multipart, pillow, google-genai==2.23.0 (+ pytest/httpx/respx test-only)
    app/main.py                    # FastAPI app, CORS, routes, error handlers, /healthz
    app/config.py                  # env-only settings (no defaults for secrets)
    app/db.py                      # sqlite3 connect, WAL pragma, schema init
    app/db/schema.sql              # DDL (mirrors DATABASE.md)
    app/models.py                  # dataclasses / TypedDicts (no ORM)
    app/schemas.py                 # Pydantic request/response models (mirror API.md)
    app/routes/ (health, observations, journal.py)
    app/services/ai_service.py     # AIService interface + GeminiAdapter (generate_content; Interactions deferred)
    app/services/images.py         # validation, EXIF strip, re-encode, thumbnail
    app/services/journal.py        # CRUD orchestration
    data/.gitkeep                  # db + uploads live here at runtime (git-ignored contents)
```

Dependency rule: `routes → services → db/images`; `services/ai_service.py` is the **only** module that talks to the model endpoint. Routes never import HTTP clients directly.

## 3. Request lifecycle (happy path)

1. `POST /api/v1/observations/analyze` (multipart: `image`, optional `notes_hint`): `images.validate_and_store_temp()` → magic-byte check, size/dimension checks, EXIF-strip + re-encode (JPEG quality 85 / PNG optimize), 512px thumbnail. Invalid → `400/413/422` envelope (see `API.md` §6), temp file deleted.
2. `AIService.analyze(image_path, hint)` builds the constrained prompt (`AI_SYSTEM.md` §4), sends EXIF-stripped/re-encoded bytes via the Gemini API (`Part.from_bytes`, `response_mime_type="application/json"`), parses + validates JSON against `schemas.AIAnalysis`. In `ollama` mode the same contract holds via `POST {OLLAMA_HOST}/api/chat` with an `images` array (see `AI_SYSTEM.md` §2). In `auto` mode a hosted transport failure triggers exactly one local attempt; auth/bad-output faults propagate unmasked. Parse/contract failure → retry once with repair prompt; second failure → `502 ai_bad_response` (never fabricate).
3. Response returns analysis (not yet persisted). Frontend renders AI panel + empty observation form.
4. `POST /api/v1/journal-entries` (JSON: `temp_image_id | image_ref`, `ai_analysis` or null, `user_notes`, `experiment_done`, `experiment_result`): server promotes temp image to `data/uploads/{entry_id}/`, inserts rows in one SQLite transaction (see `DATABASE.md` §4), returns 201.
5. List/detail/delete are plain CRUD with `request_id` logging and standard error envelope.

Timeouts: SDK client 120s; Uvicorn/route 150s; reverse-proxy/client 180s (all provisional pending the five-run latency log). In `auto` mode the hosted attempt is additionally bounded by `AUTO_PRIMARY_TIMEOUT_S` (default 60s), so worst case is 60s + one full local attempt. On timeout → `504 ai_timeout` + retry UI. No partial saves. One analysis runs at a time (single inference slot; a second concurrent analyze gets `503 ai_busy`).

## 4. Configuration (env-only; see SECURITY.md §2)

| Var | Required | Example | Notes |
|-----|----------|---------|-------|
| `DATABASE_PATH` | No (default `data/verdantra.db`) | `data/verdantra.db` | — |
| `UPLOAD_DIR` | No (default `data/uploads`) | `data/uploads` | Served read-only under `/media/` |
| `GEMINI_API_KEY` | Yes for AI | *(secret — env-only, never committed, logged, or printed)* | Read from process environment; startup presence-check without printing value. Unused in `ollama` mode |
| `AI_PROVIDER` | No (default `gemini`) | `gemini` | `gemini` (hosted), `ollama` (local-only), or `auto` (hosted first, one local fallback); anything else fails fast at startup — never a silent fallback |
| `AI_MODEL_ID` | No (default `gemma-4-26b-a4b-it`) | `gemma-4-26b-a4b-it` | Recorded in every analysis row |
| `AI_TIMEOUT_S` | No (default `120`, provisional) | `120` | Pending five-run latency test |
| `TRANSMIT_MAX_EDGE` | No (default `2048`) | `2048` | Provider-payload longest edge in px; stored files unaffected |
| `TRANSMIT_JPEG_QUALITY` | No (default `82`) | `82` | JPEG quality for the provider payload only |
| `GEMINI_MAX_OUTPUT_TOKENS` | No (default `1024`) | `1024` | Bounds hosted output length, cost, and latency |
| `OLLAMA_NUM_CTX` | No (default `4096`) | `4096` | Ollama context window (one image + prompt needs far less than 128K) |
| `OLLAMA_NUM_PREDICT` | No (default `1024`) | `1024` | Ollama output cap, mirroring the hosted bound |
| `OLLAMA_KEEP_ALIVE` | No (default `5m`) | `5m` | How long Ollama keeps the model resident; one model at a time |
| `AUTO_PRIMARY_TIMEOUT_S` | No (default `60`, provisional) | `60` | Hosted-attempt bound in `auto` mode only; fallback keeps full `AI_TIMEOUT_S` |
| `OLLAMA_NUM_THREAD` | No (default `0` = server default) | `0` | Requested CPU threads for Ollama inference; set 2–4 to trade speed for thermals |
| `OLLAMA_HOST` | No (default `http://localhost:11434`) | `http://localhost:11434` | Local only; used solely in `ollama` mode |
| `OLLAMA_MODEL` | No (default `gemma4:e2b`) | `gemma4:e2b` | Recorded in every analysis row in `ollama` mode |
| `CORS_ORIGINS` | Yes in prod | `https://verdantra.example.com` | Dev default `http://localhost:5173` |
| `MAX_IMAGE_MB` | No (default `10`) | `10` | Mirrors API contract |

`.env` is git-ignored; `.env.example` lists the above with safe placeholders only.

## 5. Data + file handling summary

SQLite WAL mode (`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`), one writer (FastAPI default single-process in MVP; document that `--workers 1` is required until write-queue hardening). Images never stored as BLOBs — filesystem paths in DB, files on disk; delete cascades to files in the same transaction scope (delete files after commit; on crash, orphan sweep documented in `DATABASE.md` §6). Full DDL in `DATABASE.md`.

## 6. Deployment architecture (MVP vs future — do not conflate)

**MVP (binding): app tier only on a DigitalOcean Basic CPU Droplet.**

- Proposed size: **Basic, 2 vCPU / 4 GB RAM / 80 GB, Ubuntu 24.04** (~$12/mo range at research time — verify live pricing; do not quote as fact in user-facing copy).
- Option A (documented default): single Droplet running Uvicorn (`--host 127.0.0.1 --port 8000 --workers 1`) behind Caddy/Nginx (TLS via Let's Encrypt) serving both `/api/*` and the built Vite `dist/`. Option B: Droplet for API + DigitalOcean App Platform static site for frontend — deferred unless maintainer prefers it.
- **Model runs on Google infrastructure via the Gemini API (time-boxed M1–M5).** The builder machine runs the app only. If a future revision must serve AI itself, that requires re-verification and is out of the one-day budget.
- No managed database, no Spaces, no load balancer, no container registry in MVP. Backups = documented manual `sqlite3 .backup` + `rsync` of `data/` (see `DATABASE.md` §6).

## 7. Hardware, model compatibility, and costs (honest accounting)

| Item | Verified at doc time | MVP implication |
|------|----------------------|-----------------|
| Gemma 4 26B A4B via Gemini API (text+image→text), 256K context | Yes — supported-model list + image-input example (`gemma_on_gemini_api`); `google-genai` 2.23.0 verified | Active path (time-boxed M1–M5); latency/cost/quota pending measurement |
| Quota (screenshot-observed, not guarantees) | Project `gemma-4`, Free tier: 30 RPM / 16K TPM / 14.4K RPD shown; usage 1 / 312 / 1 at screenshot time | Re-check live on any 429; per-model values unconfirmed |
| Prior E2B/Ollama local path | Existed as v0.1.0 default; impractical on this host | Retained alternative, not active; reactivation needs a new coordinated change |
| Ollama `gemma4:e2b` offline (registry `vision` tag, ~4.6 GB pull, CPU-capable) | Image support per official Ollama vision docs; **not live-tested here** | Opt-in via `AI_PROVIDER=ollama`; verify with a real photo before claiming offline vision works |
| Auto failover (hosted first, one local attempt) | Transport-failure triggers only; worst case costs both timeouts back-to-back | Opt-in via `AI_PROVIDER=auto`; live fallback unverified — measure before promising |
| DO CPU Droplets ($4+/mo Basic at research time) | Yes — DO Droplet docs | MVP app host; verify live price at deploy time |
| DO GPU Droplets (RTX4000 20GB → H100 80GB → H200/MI300X; on-demand ~$1.57+/hr L40s-class, ~$6+/hr H100-class at research time; inference image lists Llama/Mistral, **not Gemma 4**) | Partially verified; prices/regions change frequently | **Out of MVP.** Future GPU path needs: (a) region with stock, (b) Gemma 4 E2B test on that GPU image or manual vLLM/Transformers install, (c) written budget approval. No GPU deployment is claimed in MVP |
| `google-genai` 2.23.0 SDK (`generate_content` verified; Interactions surface present but deferred) | Verified locally (signatures + package contents); per-tag behavior confirmed only for the reported smoke run | If `generate_content` regresses, MVP is blocked — do not silently swap API shapes without updating all docs |

Cost guidance for docs/UI: state only "App hosting is a small CPU Droplet (a few dollars per month — check current DigitalOcean pricing); AI is metered per-request API usage under a $0-spend posture (billing not enabled; no cap exists — any future cap needs explicit approval)." Never state a total, a per-call price, or an SLA.

## 8. Observability (minimal, one-day-appropriate)

- `GET /healthz` → `{ status, db, ai, model_id, version, uptime_s }` (`ai: ok|unavailable`, never fake `ok`).
- Structured logs: `{ ts, level, request_id, route, ms, ai_model, ai_ms, error_code? }` to stdout; no PII (no image bytes, no full notes — log lengths only).
- Frontend: `request_id` shown on every error card for bug reports.

## 9. Architecture acceptance

- [ ] Structure in §2 created exactly; `ai_service.py` is the sole model boundary.
- [ ] Analyze → save → list → detail → delete works end-to-end on the verified AI path.
- [ ] Forced provider outage (invalid key / simulated 429 / timeout) yields honest `503`/`504` + UI retry state (no fabricated analysis).
- [ ] `--workers 1` documented; concurrent-write smoke (2 rapid saves) passes without DB lock errors surfacing as 500s (retry-once on `SQLITE_BUSY`, else `503 db_busy`).
- [ ] No GPU, queue, cache, or external DB introduced during MVP.

*Next: `AI_SYSTEM.md` for the model contract, prompts, and safety rules.*
