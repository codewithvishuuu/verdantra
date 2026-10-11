# Verdantra — User Flows (USER_FLOWS.md)

**Version:** 0.1.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP
**Depends on:** `PRD.md` (US-1–US-7), `DESIGN.md` (§§4–5), `API.md`, `AI_SYSTEM.md`

Notation: `→` user action, `⇢` system response. Error branches reference `API.md` §6 codes. All AI surfaces carry the `AI PREDICTION — UNVERIFIED` badge; all user-written surfaces carry `YOUR OBSERVATION — CONFIRMED BY YOU` (see `DESIGN.md` §4).

## Flow 1 — Photograph → AI analysis (US-1, US-2)

**Entry:** user opens `/` (New observation). **Precondition:** backend reachable (`/healthz` ok or degraded-but-up).

1. → User chooses `Take photo / Upload` (file picker; mobile offers camera via `capture="environment"`).
2. ⇢ Client pre-validates (JPEG/PNG/WebP, ≤ 10 MB) and shows thumbnail + filename + size. Invalid → inline `role="alert"` message, no network call.
3. → User optionally adds a ≤ 280-char context hint ("on the park path after rain") and presses `Analyze photo`.
4. ⇢ Button enters loading state (`Analyzing…`, disabled), skeleton panel reads "Examining visible evidence… this can take a minute or more (provisional 150 s timeout; one owner-reported sample ~47.4 s, five-run log pending)". Client sends `POST /api/v1/observations/analyze` (multipart).
5. ⇢ Success (200): AI panel renders — `observed_features` bullets, `cautious_explanation` paragraph, `⚠ uncertainty` lines, experiment card (title, materials, steps, safety callout, ~minutes), subline `Model: gemma-4-26b-a4b-it · {timestamp}`. User observation form appears below, empty.
6. **Branches:**
   - `400 invalid_image / 413 too_large / 422 unusable_image` → error card with message + `Try a different photo`; draft preserved.
   - `503 ai_unavailable / 504 ai_timeout / 502 ai_bad_response` → amber panel per `DESIGN.md` §5 ("AI helper unavailable… you can still write and save your own observation") + `Retry analysis` button; photo retained.
   - AI safety redirect (valid 200 whose explanation states a boundary, e.g., person in frame) → panel renders normally; copy explains the limitation.

**Done when:** user sees either an AI panel or an honest failure state; no fabricated result is ever shown.

## Flow 2 — Try the experiment + record what happened (US-3)

**Entry:** AI panel visible (or AI-unavailable panel with save-without-AI allowed).

1. → User reads the suggested experiment and does it outdoors (outside the app — e.g., compare sunny vs shaded leaf, count ripples, sketch bark).
2. → User writes `Your notes` (required, 1–2000 chars: what they did / saw), ticks `I tried the experiment` if true, optionally writes `What happened` (≤ 2000 chars). Numbers, if any, come only from the user.
3. ⇢ Live char count + inline validation (empty notes → "Write at least a sentence about what you saw" on submit attempt).
4. → User presses `Save to journal`.
5. ⇢ Client sends `POST /api/v1/journal-entries`; success (201) → toast/confirmation + redirect to `/journal/{id}` detail. Failure → error card with `request_id`, draft preserved in form state.

**Done when:** entry is persisted and user lands on its detail view. AI text is stored read-only; only user fields are editable-before-save.

## Flow 3 — Revisit the field journal (US-4, US-5)

**Entry:** user opens `/journal`.

1. ⇢ List loads via `GET /api/v1/journal-entries` (newest first): thumbnail, title, date, badges (`AI included` / `Experiment done`). Empty journal → empty-state card + CTA to `/`.
2. → User selects an entry → `/journal/:id` loads via `GET /api/v1/journal-entries/{id}`: full image, AI panel (read-only, model + timestamp) beside/below user panel, matching `DESIGN.md` §4.
3. **Branches:** entry deleted elsewhere → `404` card ("This entry no longer exists") + back link; list fetch fails → error card + `Retry`.

**Done when:** user can distinguish, on one screen, what the model guessed from what they confirmed.

## Flow 4 — Delete an entry (US-6)

**Entry:** detail view `/journal/:id`.

1. → User presses `Delete entry` → confirm dialog ("Delete this entry and its photo? This cannot be undone.", focus-trapped, Esc cancels).
2. → User confirms → `DELETE /api/v1/journal-entries/{id}` → 204 → redirect to `/journal` with "Entry deleted" confirmation.
3. **Branch:** delete fails (already gone → 404; server error → 5xx card) → dialog stays informative, no silent disappearance.

## Cross-cutting rules (all flows)

- **Draft preservation:** uploaded photo preview + typed notes survive API errors and AI retries within the session (no localStorage persistence required in MVP).
- **No-login consequence:** journal is per-browser-profile only insofar as it is server-side single-tenant; document in UI footer ("Journal lives on this demo server — entries are shared on this device setup").
- **Safety copy:** footer + experiment card always show "Be safe outdoors. Never eat, touch, or approach anything because the AI suggested it."
- **Instrumentation:** every error card shows `request_id`; every AI panel shows `model_id + timestamp`.

## Flow acceptance (testable walkthroughs)

- [ ] F1: valid JPEG → AI panel or honest AI-outage panel within timeout; invalid file → client rejection without network call.
- [ ] F2: empty notes block save with inline message; valid notes → 201 → detail shows both badges.
- [ ] F3: two saved entries list newest-first; detail shows image + both panels; 404 path renders friendly card.
- [ ] F4: delete → 204 → entry absent from list and `GET` → 404; image files removed from `data/uploads/{id}/`.

*Next: `API.md` for exact request/response contracts these flows depend on.*
