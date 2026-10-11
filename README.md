# Verdantra 🌱 — AI-powered outdoor discovery & field science

> Photograph something outdoors → get a cautious AI reading + a safe mini-experiment → record what *you* observed in your field journal.
> **Predictions are unverified. Your observations are the record that counts.**

**Status:** 📄 Documentation v0.2.0 (hosted time-box re-baseline for M1–M5; permanent adoption gated on Phase 5). No application code yet beyond the verified frontend build and the reported M0-A smoke script. This README is the front door; the build follows `IMPLEMENTATION_PLAN.md`.

- Docs: [`PRD.md`](PRD.md) · [`DESIGN.md`](DESIGN.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`AI_SYSTEM.md`](AI_SYSTEM.md) · [`USER_FLOWS.md`](USER_FLOWS.md) · [`API.md`](API.md) · [`DATABASE.md`](DATABASE.md) · [`SECURITY.md`](SECURITY.md) · [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)
- Stack: React 18+ · TypeScript · Vite · Tailwind CSS · Python 3.11+ · FastAPI · SQLite · Gemma 4 26B via hosted Gemini API (time-boxed M1–M5; permanent adoption gated)
- Deploy target: DigitalOcean CPU Droplet for the app tier (server GPU explicitly out of MVP — see §8)

## 1. What Verdantra does (MVP)

1. **Upload/take an outdoor photo** (JPEG/PNG/WebP, ≤ 10 MB) on the New-observation page.
2. **Get an AI analysis** — visible features, a hedged explanation, explicit uncertainty, and exactly one safe household-materials experiment (10 min or less).
3. **Write your own notes** (what you did / saw) and **save** photo + AI output + notes as a journal entry.
4. **Revisit/delete** entries in your field journal. AI panels always read `AI PREDICTION — UNVERIFIED`; your words always read `YOUR OBSERVATION — CONFIRMED BY YOU`.

What it does **not** do: identify species for certain, advise eating/touching/treating anything, track location, sync across accounts, or work offline. Full scope + deferrals: `PRD.md` §§4/8.

## 2. Visual identity

The provided **Verdantra logo** is the visual identity and must not be redesigned without permission. At documentation time no logo file was present in the repo (empty working directory on inspection) — the build creates `assets/logo/` as a verbatim drop-in slot with a wordmark fallback (see `DESIGN.md` §2). Do not generate an AI replacement logo.

## 3. Quickstart (after Milestone 1 scaffolds exist)

```bash
# prerequisites (verify versions, record in build PR):
python --version   # >= 3.11 (3.11 carries google-genai for the smoke path)
node --version     # >= 20
# No local model runtime needed: inference is hosted (gemma-4-26b-a4b-it via Gemini API)

# backend (from backend/)
cp ../.env.example .env 2>/dev/null || cp .env.example .env
# edit .env: GEMINI_API_KEY=<your key, env-only, never committed>, CORS_ORIGINS=http://localhost:5173
# offline mode instead: AI_PROVIDER=ollama  (needs local Ollama + gemma4:e2b; no key, no Google traffic)
# automatic failover: AI_PROVIDER=auto  (tries hosted first, one local attempt on transport failure; verify live first)
pip install -r requirements.txt
python -m sqlite3 ../data/verdantra.db < app/db/schema.sql
uvicorn app.main:app --reload --workers 1
curl -s localhost:8000/healthz   # expect {"status":"ok|degraded","db":"ok","ai":"ok|unavailable",...}

# frontend (from frontend/)
npm install && npm run dev       # http://localhost:5173 (proxies /api → :8000)
```

If the hosted smoke check (`smoke/gemma_api_smoke.py`) or the five-run latency log in `AI_SYSTEM.md` §8 fails, **stop** — the MVP is blocked until the log records a passing backend. Do not substitute another model family without updating all docs.

## 4. Project structure (to be created in Milestone 1)

```
verdantra/
  *.md  .gitignore  .env.example  assets/logo/
  frontend/  (vite + react + tailwind; src/pages, src/components, src/lib/api.ts)
  backend/   (fastapi; app/main.py, routes/, services/ai_service.py + images.py, db/schema.sql)
  data/      (git-ignored at runtime: verdantra.db + uploads/)
```

Source of truth per area: API → `API.md`, DB → `DATABASE.md`, AI → `AI_SYSTEM.md`, design → `DESIGN.md`, flows → `USER_FLOWS.md`, plan → `IMPLEMENTATION_PLAN.md`.

## 5. API & data in 30 seconds

- `GET /healthz` — app + DB + AI reachability (honest `ai: ok|unavailable`).
- `POST /api/v1/observations/analyze` (multipart `image` + optional `notes_hint`) → validated `AIAnalysis` JSON or a standard error (`ai_unavailable`/`ai_timeout`/`ai_bad_response`).
- `POST /api/v1/journal-entries` → save photo + frozen AI snapshot + your notes (201); `GET` list/detail; `DELETE` removes rows + image files.
- Errors always look like `{"error":{"code":"…","message":"…","details":{…}},"request_id":"…"}`. Full contracts: `API.md`; DDL + transactions: `DATABASE.md`.

## 6. AI position in one paragraph

MVP uses **`gemma-4-26b-a4b-it` via the hosted Gemini API (time-boxed M1–M5)** — instruction-tuned Gemma 4 MoE (3.8B active params), text+image→text, 256K context, called with `google-genai` 2.23.0 `generate_content` behind the `AIService` interface. Offline alternative (opt-in): `AI_PROVIDER=ollama` runs local `gemma4:e2b` with no cloud traffic — live image verification still pending, so offline vision is not claimed working yet. The prior E2B/Ollama local path is retained as a documented alternative, not the active path. Permanent hosted adoption is gated on Phase 5 verification. `AI_PROVIDER=auto` tries hosted first with one local fallback on transport failure (live fallback unverified). Prompts, uncertainty rules, and refusal policy: `AI_SYSTEM.md` §§4–6.

## 7. Privacy & safety (read before deploying)

- **Photos you analyze leave this host** as EXIF-stripped copies sent to Google's Gemini API; temp images from un-saved analyses are swept within an hour.
- ⚠️ **Free-tier limitation:** on the current Free tier, Google may use submitted content to improve its products, including human review. Analyze only your own non-sensitive, consented photos. No paid-tier privacy applies unless a tier change is independently confirmed. **$0-spend posture: billing is not enabled; no spend cap exists.**
- **No accounts, no analytics, no location columns** by design. Don't type personal data into the optional hint (placeholder warns as much).
- **Safety:** be safe outdoors; never eat, touch, or approach anything because the AI suggested it. The model gives no foraging/medical/survival advice and no definitive IDs — refusals return safe completions (`AI_SYSTEM.md` §6). Delete anytime in-app; data runbook: `DATABASE.md` §5.
- **Secrets:** zero in git (`.env` ignored, `.env.example` placeholders only; pre-push greps in `SECURITY.md` §2). Full controls: `SECURITY.md`.

## 8. Deployment & costs (honest version)

- **MVP deploys the app tier only** to a DigitalOcean Basic CPU Droplet (proposed 2 vCPU / 4 GB, Ubuntu 24.04; Uvicorn `--workers 1` behind Caddy/Nginx + TLS). Model inference runs on Google infrastructure via the Gemini API (time-boxed M1–M5).
- **Server-side GPU is out of MVP**, and AI spend stays at **$0** (billing not enabled; exact 26B per-request price unverified — third-party aggregators suggest ~$0.04–0.13 input / $0.20–0.40 output per 1M, unverified). Any future spend cap is unresolved and needs explicit approval.
- No uptime/latency SLA is claimed until Milestone 0 measures real numbers on real hardware.

## 9. Contributing (docs phase rules)

1. Read `PRD.md` §8 deferral freeze — no auth/maps/social/offline/GPU PRs during MVP.
2. Keep the 10 docs consistent: changing stack, routes, schema, prompts, or scope means updating every affected doc in the same PR.
3. Distinguish predictions from observations in every UI string; label doc examples `EXAMPLE — not a real result`.
4. Never commit secrets, DB files, uploads, or generated logos. Follow the acceptance checklists in `IMPLEMENTATION_PLAN.md` §5 and `SECURITY.md` §9.

## 10. License & model terms (maintainer to confirm)

- Proposed app-code license: **MIT** (maintainer confirms; add `LICENSE` at build start).
- Gemma 4 weights: **Apache 2.0** under Google's Gemma terms — review the model card + Hugging Face repo terms before distributing weights or derivatives.
- No deployment, accuracy, or availability claims are made in these docs beyond what is explicitly marked verified.

*Start here for the build: `IMPLEMENTATION_PLAN.md` §2 (first task: confirm the reported hosted smoke + five-run latency log).*
