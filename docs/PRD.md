# Verdantra — Product Requirements Document (PRD)

**Version:** 0.2.0 (hosted time-box re-baseline for M1–M5; permanent adoption gated on Phase 5)
**Date:** 2026-10-09
**Status:** Draft for MVP build. No application code exists yet beyond the verified frontend build and the reported M0-A smoke script.
**Repo state at time of writing:** Empty working directory (`Hacktoberfest week 1`). No source files, no assets, no provided logo file found on disk. See §9 and `README.md`.
**Companion docs:** `DESIGN.md`, `ARCHITECTURE.md`, `AI_SYSTEM.md`, `USER_FLOWS.md`, `API.md`, `DATABASE.md`, `SECURITY.md`, `IMPLEMENTATION_PLAN.md`, `README.md`

Technical references consulted (do not treat as deployment guarantees):

- Google AI for Developers — Gemma 4 model card (`ai.google.dev/gemma/docs/core/model_card_4`): Gemma 4 family (E2B, E4B, 12B Unified, 26B A4B, 31B), Apache 2.0, multimodal text+image input / text output (audio on E2B/E4B/12B), 128K context (E2B/E4B) / 256K (larger), variable resolution images.
- Hugging Face — `google/gemma-4-E2B`, `google/gemma-4-12B`, `google/gemma-4-31B` model pages.
- Ollama library — `gemma4` (E2B/E4B/12B/26B/31B tags), `gemma3` family.
- Google AI for Developers — Run Gemma with the Gemini API (`ai.google.dev/gemma/docs/core/gemma_on_gemini_api`): `gemma-4-26b-a4b-it` supported with image input; `google-genai` 2.23.0 SDK signatures verified locally.
- DigitalOcean Docs — Droplet Features (verified 2026-09-03): CPU Droplets (Basic/General Purpose/CPU-Optimized/etc.), GPU Droplets (RTX 4000 20GB, RTX 6000 48GB, L40s 48GB, H100 80GB, H200 141GB, MI300X 192GB), AI/ML-ready images; inference-optimized image currently lists Llama/Mistral models only — **Gemma 4 is NOT listed there at time of writing**.

> Rule applied throughout: **do not assume a model is available on a particular inference service until verified.** Every inference path in this PRD requires an explicit verification step before build (see `AI_SYSTEM.md` §2 and `IMPLEMENTATION_PLAN.md` Milestone 0).

---

## 1. Product concept (one paragraph)

Verdantra is an open-source, AI-powered outdoor discovery and field-science web app. A user photographs a real-world natural object or outdoor scene (leaf, bark, rock, puddle, sky, insect on a leaf — anything outdoors and safe to observe). A compatible Gemma 4 multimodal model analyzes only what is visibly evidenced in the image, generates a cautious, plain-language explanation with explicit uncertainty, and suggests one safe, simple outdoor science experiment the user can try with household materials. The user then records what they actually did and saw in their own words and saves the result in a personal field journal. The system must always visually and textually distinguish **model predictions** from **user-confirmed observations** and must never invent measurements, species IDs, test results, or facts.

## 2. Problem and goals

**Problem:** People notice interesting things outdoors but lack a low-friction, honest way to ask "what might this be?", try a tiny experiment, and keep a record — without being misled by overconfident AI.

**MVP goals (all must be met for MVP acceptance):**

1. G1 — A user can submit a photo and receive a cautious AI analysis + one safe experiment suggestion within the provisional 150 s route timeout (five-run latency log pending; no SLA promised).
2. G2 — A user can record their own observation text and save the photo + AI output + own notes as a journal entry.
3. G3 — A user can list, view, and delete their journal entries.
4. G4 — Every screen that shows AI output labels it as an unverified prediction; every user-written field is labeled as a user-confirmed observation.
5. G5 — The project is deployable as documented to a DigitalOcean CPU Droplet for the app tier; model/GPU compatibility is verified separately and **server-side GPU is explicitly out of MVP scope** (see §7).

**Non-goals for MVP:** species identification guarantees, medical/foraging/survival advice, social features, accounts/sync, maps, gamification, offline mode, native apps, multi-user collaboration (full list in §8).

## 3. Target users

- Primary: curious beginners (students, families, hobby naturalists) on desktop or mobile browsers who want a guided, safe outdoor activity.
- Secondary: educators running a 10-minute outdoor demo.
- Explicitly out of scope: researchers needing calibrated instruments, foragers, clinicians, or anyone needing authoritative identification. The product must say so in UI copy (see `AI_SYSTEM.md` §5).

## 4. MVP scope — must-have user stories

| ID | Story | Acceptance (testable) |
|----|-------|-----------------------|
| US-1 | As a user, I can upload or take a photo (JPEG/PNG/WebP, ≤ 10 MB) and see client-side validation errors for wrong type/size. | Upload of a valid 2 MB JPEG succeeds; upload of a 25 MB file or `.exe` is rejected with messages defined in `API.md` §6. |
| US-2 | As a user, I can get an AI analysis of visible evidence (observed features, cautious explanation, uncertainty, one experiment suggestion). | Given a valid photo, `POST /api/v1/observations/analyze` returns the contract in `API.md` §3.1 within timeout; UI renders "AI PREDICTION (unverified)" badge. No species claim is stated as fact; see `AI_SYSTEM.md` §4. |
| US-3 | As a user, I can enter my own observation notes (what I did / what I saw) alongside the AI output before saving. | Journal-entry create form requires non-empty user notes (1–2000 chars); AI text is read-only and separately badged. |
| US-4 | As a user, I can save the photo + AI output + my notes as a journal entry and see it in a list. | `POST /api/v1/journal-entries` → 201 with id; entry appears in `GET /api/v1/journal-entries` list. |
| US-5 | As a user, I can open a past entry and see photo, AI prediction (with timestamp + model id), and my confirmed observation side by side. | Detail view shows both sections with distinct badges per `DESIGN.md` §4. |
| US-6 | As a user, I can delete an entry (and its stored image). | `DELETE /api/v1/journal-entries/{id}` → 204; subsequent GET → 404; image file removed from disk. |
| US-7 | As a user, I see honest failure states when AI is unavailable, image is unusable, or input is unsafe. | Forced AI outage returns `503 ai_unavailable` envelope per `API.md` §6 and UI retry copy; no fake result is ever synthesized. |

All stories assume single-user, single-device use with no login (see §7 decision D3).

## 5. Functional requirements (MVP)

1. F1 Photo intake: file picker + mobile camera capture (`<input type="file" accept="image/*" capture="environment">`); client pre-check (type, ≤ 10 MB); server re-validates (type via magic bytes, size, min 64×64 px, max 4096 px longest edge, re-encode + strip EXIF GPS by default). See `SECURITY.md` §4.
2. F2 AI analysis: backend `AIService` abstraction calls the verified Gemma 4 path (hosted `gemma-4-26b-a4b-it` via the Gemini API, time-boxed M1–M5; see `AI_SYSTEM.md` §2). Prompt constrains output to JSON matching `API.md` §3.1: `observed_features[]`, `cautious_explanation`, `uncertainty[]`, `experiment {title, steps[], materials[], safety_notes[], estimated_minutes}`, `model_id`, `disclaimer`. Free-form model text is never rendered; only parsed fields are.
3. F3 Experiment suggestion: exactly one experiment per analysis; must be safe, outdoor, no-fire/no-chemicals/no-consumption/no-wildlife-disturbance; must include safety notes. Unsafe requests are refused with a safe-completion message (see `AI_SYSTEM.md` §6).
4. F4 Observation capture: free-text fields `user_notes` (required), `experiment_done` (boolean), `experiment_result` (optional). No numeric measurements are auto-filled; any numbers shown come verbatim from user input.
5. F5 Field journal: list (newest first, thumbnail + title + date), detail, delete. No edit in MVP (delete + recreate instead — keeps scope to one day).
6. F6 Branding: provided Verdantra logo displayed in header; **do not redesign it without permission**. Logo file was not found in repo — placeholder slot + documented asset pipeline required (see §9, `DESIGN.md` §2).
7. F7 Health check: `GET /healthz` returns app + DB + AI reachability status (see `API.md` §2).

## 6. Non-functional requirements

- NFR-1 Stack lock (no substitutes without updating all docs): Frontend React 18+ / TypeScript 5+ / Vite 5+ / Tailwind CSS 3.4+; Backend Python 3.11+ / FastAPI 0.115+ / Uvicorn; DB SQLite (stdlib `sqlite3`, WAL mode, single file `data/verdantra.db`); AI via documented Gemma 4 path only.
- NFR-2 Performance target (not a guarantee): p50 analyze target pending the five-run log (one reported sample ~47.4 s, not independently measured); list/detail < 500 ms locally. No production SLA is claimed.
- NFR-3 Privacy: images stored locally on app host under `data/uploads/`; EXIF GPS stripped by default; no third-party analytics/tracking in MVP; sanitized image bytes leave the host only to the Gemini API endpoint. Free-tier data-use limitation applies (Google may use content for product improvement, incl. human review) — see `SECURITY.md` §5.
- NFR-4 Accessibility: WCAG 2.2 AA intent — semantic HTML, keyboard-reachable flows, visible focus, alt text, color contrast ≥ 4.5:1 for body text, form labels programmatically associated. Full checklist in `DESIGN.md` §6.
- NFR-5 Reliability: standardized error envelope (`error.code`, `error.message`, `error.details`, `request_id`) for all 4xx/5xx; frontend never crashes on API error; AI timeout chain 120 s SDK / 150 s route / 180 s proxy (all provisional pending the five-run log).
- NFR-6 Open source: Apache-2.0-compatible posture (Gemma weights are Apache 2.0; app code license to be confirmed by maintainer — default proposal MIT, flagged as decision D6); `README.md` documents license + model terms + data policy.
- NFR-7 Secrets: zero secrets in git. Env-only config (`.env` ignored, `.env.example` committed). See `SECURITY.md` §2.

## 7. Key product/technical decisions (binding)

- D1 **Model choice:** MVP model is **`gemma-4-26b-a4b-it` via the hosted Gemini API (time-boxed M1–M5)** — instruction-tuned Gemma 4 MoE, chosen after local E2B inference proved impractical on the builder machine. Permanent adoption gated on Phase 5 verification. Prior E2B/Ollama local path retained as documented alternative. Rationale and verification in `AI_SYSTEM.md` §§1–2, 8.
- D2 **Inference implementation (documented, verified path):** `GeminiAdapter` (`google-genai` 2.23.0 `generate_content`, JSON output config, Pydantic validation, at most one repair retry) behind the `AIService` interface. Interactions API migration deferred. Build may not start Milestone 1 until the five-run latency log passes and the active path is recorded in `AI_SYSTEM.md` verification log.
- D3 **No login in MVP:** single-user, single-device journal. Rationale: auth would break the one-day budget. Multi-user/auth deferred. Consequence: no cross-device sync; deploy is single-tenant demo.
- D4 **SQLite, no ORM migrations in MVP:** stdlib `sqlite3`, schema in `backend/app/db/schema.sql`, `schema_version` table, WAL mode. Alembic/SQLAlchemy deferred.
- D5 **Deployment split:** MVP deploys the **app tier only** to a DigitalOcean Basic CPU Droplet (proposed: 2 vCPU / 4 GB RAM, Ubuntu 24.04, Docker or systemd + Uvicorn + static frontend). Server-side GPU inference is **out of MVP** — costs ($1.57+/hr L40s-class on-demand at time of research; H100-class ~$6+/hr) and availability make it incompatible with a one-day MVP. Model inference runs via the hosted Gemini API (time-boxed M1–M5); no Droplet GPU. GPU path is a documented future option pending budget + region + model verification (see `ARCHITECTURE.md` §7).
- D6 **License proposal:** MIT for app code (maintainer to confirm); Gemma weights remain Apache 2.0 under Google's terms; ShieldGemma-style safety classifier deferred, safety handled via prompt + validation rules in MVP.

## 8. Explicitly deferred (not MVP)

Accounts/login, multi-device sync, social/sharing, map/GPS trails, species database integration, offline PWA, push notifications, i18n, admin panel, analytics dashboard, automated tests beyond smoke checklist (unit/integration suites deferred to post-MVP), CI/CD pipeline, backups beyond documented manual SQLite copy, Droplet-hosted GPU inference, video/audio input, 12B+ local models, fine-tuning, content moderation service integration.

## 9. Constraints, risks, unknowns

1. **Logo asset missing.** Requirement says "use the provided Verdantra logo" but no logo file exists in the inspected repo (empty directory). Risk: implementer invents a logo, violating the constraint. Mitigation: `assets/logo/` placeholder + `DESIGN.md` §2 asset pipeline; build blocked on logo drop-in without redesign.
2. **Hosted-inference unknowns.** One owner-reported smoke sample (~47.4 s, not independently measured); latency distribution, per-request cost, and quota behavior on this key are unmeasured. Free-tier content may be used by Google for product improvement incl. human review; key handling and $0-spend posture must hold. Mitigation: five-run latency log + spend/quota evidence in M5; no permanent adoption before Phase 5; never present predictions as facts.
3. **AI overconfidence risk.** Field-science misidentification could cause unsafe behavior (eating plants, approaching wildlife). Mitigation: prompt guardrails + UI badges + refusal rules (`AI_SYSTEM.md` §§4–6); never present predictions as facts.
4. **One-day budget risk.** Scope is tight by design; any added feature breaks the plan. Mitigation: `IMPLEMENTATION_PLAN.md` timeboxes; deferral list is binding.
5. **Cost risk.** GPU Droplets are 100–1000× the cost of a Basic CPU Droplet, and hosted API usage is metered per request (exact 26B row unverified). Mitigation: GPU excluded from MVP; **$0-spend posture holds — billing is not enabled and no spend cap exists** (any future cap needs explicit approval); cost table in `ARCHITECTURE.md` §7 uses only observed ranges, labeled as subject to change with links to live pricing.

## 10. Acceptance criteria (MVP sign-off)

- [ ] All US-1–US-7 pass against `API.md` contracts using the verification checklist in `IMPLEMENTATION_PLAN.md` §5.
- [ ] Prediction-vs-observation badges visible on analyze + detail screens (screenshot in PR review).
- [ ] `GET /healthz` reports `db: ok` and `ai: ok|unavailable` honestly; forced AI outage shows honest 503/504 UI state (including new `api_*` codes), not fake data.
- [ ] No secrets in repo (`git grep` for `sk-`, `hf_`, `AIza`, `BEGIN PRIVATE KEY`, `.env` absent; `.env.example` present).
- [ ] Logo slot uses the provided logo file once supplied; no redesign.
- [ ] Docs state only verified facts; any illustrative example values are labeled `EXAMPLE — not a real result`.
- [ ] App runs from a clean checkout following `README.md` quickstart (frontend `npm run dev`, backend `uvicorn app.main:app`), with Milestone 0 AI verification log holding the reported pass plus the five-run log.

---

*End of PRD. Next: `DESIGN.md` for visual identity, `ARCHITECTURE.md` for system structure.*
