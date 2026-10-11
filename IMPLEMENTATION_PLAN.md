# Verdantra — Implementation Plan (IMPLEMENTATION_PLAN.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP (hosted time-box re-baseline for M1–M5)
**Depends on:** all preceding docs · **Budget:** one working day (~8h) · **Code:** not started (docs-only task; do not install packages yet)

## 1. Build order and timeboxes (stop-and-cut rules apply)

| Milestone | Timebox | Work | Done when (§5 check) |
|-----------|---------|------|----------------------|
| M0 — Verify AI + host | 1h, blocks all else | Record reported hosted smoke (`gemma-4-26b-a4b-it` via Gemini API, ~47.4 s reported single sample) + run five-run latency log; confirm Python 3.11+ (`google-genai` 2.23.0), sqlite3 ≥ 3.35, Node 20+. If hosted path FAILS, STOP and re-plan (no silent model swap). | §8 log filled (reported pass + five-run log); `AI_BACKEND=gemini` + `AI_MODEL_ID=gemma-4-26b-a4b-it` chosen and mirrored in `ARCHITECTURE.md` §4 |
| M1 — Scaffolds | 1h | Create `ARCHITECTURE.md` §2 tree, `.gitignore` + `.env.example` (`SECURITY.md` §6), `schema.sql` (`DATABASE.md` §3), backend `config/db/main/health`, frontend Vite+TS+Tailwind shell + `lib/api.ts` types (`API.md` §5). No AI logic yet. | `GET /healthz` → 200 with `ai: unavailable` honest; frontend builds |
| M2 — Images + analyze | 2h | `services/images.py` (validate/strip/re-encode/thumb) + `POST /observations/analyze` + `ai_service.py` GeminiAdapter + prompt (`AI_SYSTEM.md` §4) + frontend upload + AI panel (`DESIGN.md` §4). | §2 cURL returns 200-shape or honest error; UI shows badge panel or outage state |
| M3 — Journal CRUD | 1.5h | `POST/GET/DELETE journal-entries` + transactions (`DATABASE.md` §4) + list/detail/delete screens + save-without-AI path. | Round-trip save→list→detail→delete passes; files cleaned |
| M4 — Polish + safety copy | 1h | Badges, safety callouts, error cards with `request_id`, empty/loading/404 states, footer/privacy copy, favicon placeholder + logo TODO (`DESIGN.md` §2). | Keyboard-only pass + 360px/1280px no-scroll check |
| M5 — Verify + docs close-out | 1.5h | Run §5 checklist end-to-end, EXIF-strip proof, secrets grep, backup/restore dry run, fill README quickstart with measured latency, open PR with screenshots. | All §5 boxes checked; PR references this plan |

Cut rule: if any milestone overruns by > 30 min, cut M4 polish first (never cut validation, badges, or error handling). Deferred list (`PRD.md` §8) is frozen during the day.

## 2. First implementation task (do this first, ~15 min)

**M0-A (reported, pending confirmation):** hosted smoke via `smoke/gemma_api_smoke.py` returned one owner-reported PASS (~47.4 s, not independently measured; image disposition unconfirmed). Confirm with a five-run latency log (record SDK version, model ID, image bytes, latency, date per run) before M2. Do not `pip install` beyond the pinned `requirements.txt`; never print or commit the key.

## 3. Testable milestones (commands)

```bash
# M1
python -m sqlite3 data/verdantra.db < backend/app/db/schema.sql && python -m sqlite3 data/verdantra.db "PRAGMA integrity_check;"
uvicorn app.main:app --reload --workers 1            # from backend/
curl -s localhost:8000/healthz
cd frontend && npm run dev                            # + npm run build
# M2
curl -X POST localhost:8000/api/v1/observations/analyze -F "image=@smoke/leaf.jpg"
# force provider failure with a throwaway key / simulated 429 / timeout ...  # expect 503 api_auth_error / api_quota_exhausted / 504 envelopes
# M3
curl -X POST localhost:8000/api/v1/journal-entries -H 'Content-Type: application/json' -d @smoke/save.json
curl -s localhost:8000/api/v1/journal-entries | head -c 500
curl -X DELETE localhost:8000/api/v1/journal-entries/entry_XXX -v  # expect 204, then GET → 404
# M5
git ls-files | grep -E '^\.env$|\.db$|uploads/' || echo CLEAN
git grep -nE 'sk-|hf_|AIza|BEGIN PRIVATE KEY|dangerouslySetInnerHTML' -- . || echo CLEAN
python -c "from PIL import Image; from PIL.ExifTags import TAGS; im=Image.open('data/uploads/<id>/original.jpg'); print('exif:', dict(im.getexif()))"  # expect {} / no GPS
```

## 4. Risks and mitigations (build-day)

| Risk | Signal | Mitigation |
|------|--------|------------|
| Hosted latency variance (single 47.4 s reported sample) | p95 exceeds provisional 150 s | Five-run log, then finalize timeouts; cap thinking + `max_output_tokens` |
| Provider auth/quota denial | 401/429 on key or quota | Honest `api_auth_error`/`api_quota_exhausted` + save-without-AI; never fabricate; check tier/usage |
| SQLite `database is locked` | Rapid double-save | Confirm `--workers 1` + busy-timeout + retry-once; else `503 db_busy` with retry copy |
| Logo still missing at M4 | `assets/logo/` empty | Ship wordmark + TODO per `DESIGN.md` §2; never generate a replacement |
| Scope creep | Any "just add auth/maps" | Point to `PRD.md` §8 freeze; file as post-MVP issue |

## 5. Final acceptance checklist (MVP sign-off — all must pass)

- [ ] US-1–US-7 (`PRD.md` §4) demonstrated live; analyze→save→list→detail→delete round-trip recorded.
- [ ] Badges + safety copy present on analyze + detail (`DESIGN.md` §4); screenshots attached to PR.
- [ ] Forced AI outage shows amber retry state with `request_id` (including new `api_*` codes); no fabricated analysis observed in code (grep: no fallback literal analysis strings in error paths).
- [ ] EXIF GPS stripped (proof in PR, strip-before-transmit order); secrets grep clean (`AIza` included); `.env.example` placeholders only; $0-spend posture holds (no billing enabled; cap unresolved); free-tier limitation acknowledged.
- [ ] README quickstart reproduces from clean checkout; reported single-sample latency plus five-run log with variance recorded (no invented numbers).
- [ ] No deferred feature (`PRD.md` §8) present in code; no GPU/queue/auth dependency introduced.

*Next: `README.md` (project front door) and `DATABASE.md`/`SECURITY.md` runbooks referenced above.*
