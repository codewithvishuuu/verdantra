# Verdantra — API Contracts (API.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP (hosted time-box re-baseline for M1–M5)
**Depends on:** `PRD.md`, `ARCHITECTURE.md`, `AI_SYSTEM.md`, `DATABASE.md` · **Implements:** `USER_FLOWS.md`

Base URL (dev): `http://localhost:8000` · All MVP routes under `/api/v1` except `GET /healthz` and `GET /media/*`.
Content: JSON (`application/json`) except analyze (`multipart/form-data`) and media (`image/*`).
Conventions: UTF-8; timestamps RFC 3339 UTC (`2026-10-09T12:00:00Z`); ids `entry_{ulid-lowercase}` (server-generated, e.g. `entry_01k7…` — format only, example value not a real id); every error uses the envelope in §6 and header `X-Request-Id`.

Frontend client (`frontend/src/lib/api.ts`) must be typed against exactly these schemas. Backend Pydantic models (`backend/app/schemas.py`) must mirror them field-for-field.

## 1. Health

### `GET /healthz` → 200
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "ok",
  "ai": "ok",
  "model_id": "gemma-4-26b-a4b-it",
  "uptime_s": 123,
  "provider": "gemini"
}
```
- `ai`: `"ok"` only if `AIService.ping()` succeeded within 5s; else `"unavailable"` with top-level `status: "degraded"` (still HTTP 200 unless DB down → 503 with `db_unavailable`).
- `model_id`: active `AI_MODEL_ID` (must match `AI_SYSTEM.md` §8 log). No auth. Cache: `no-store`.
- `provider`: deployment mode (`gemini` | `ollama` | `auto`, additive — old clients ignore it). In `auto` mode `model_id` is the primary id until the first call, then the last producing model's id.

## 2. Analyze photo (not yet persisted)

### `POST /api/v1/observations/analyze` → 200 | 4xx | 503/502/504
Request: `multipart/form-data` — `image` (required file: JPEG/PNG/WebP, ≤ 10 MB), `notes_hint` (optional text, ≤ 280 chars).

Success 200 (`application/json`):
```json
{
  "temp_image_id": "tmp_01k7abc123",
  "image_preview_url": "/media/tmp/tmp_01k7abc123.jpg",
  "analysis": {
    "observed_features": ["oval green leaves with smooth edges", "visible central vein"],
    "cautious_explanation": "The leaves appear broad and smooth-edged, which is consistent with many common garden plants. This photo alone cannot confirm a species.",
    "uncertainty": ["Species cannot be determined from this photo", "Leaf size unclear without a reference object"],
    "experiment": {
      "title": "Sun vs shade leaf check",
      "steps": ["Find two similar leaves, one sunny and one shaded", "Look closely for 2 minutes each", "Sketch or describe any differences", "Write what surprised you"],
      "materials": ["paper", "pencil"],
      "safety_notes": ["Stay on paths", "Do not pick, touch, or taste plants"],
      "estimated_minutes": 10
    },
    "model_id": "gemma-4-26b-a4b-it",
    "disclaimer": "AI prediction based only on this photo. May be wrong. Your own observation is the record that counts.",
    "analyzed_at": "2026-10-09T12:00:00Z"
  }
}
```
> The values above are an ILLUSTRATIVE EXAMPLE — not a real model result. Never present example JSON as evidence of model behavior.

Validation order (first failure wins): missing file → `400 no_image`; magic-byte/type mismatch → `400 invalid_image`; size > 10 MB → `413 too_large`; dimensions < 64×64 or decode failure → `422 unusable_image`; hint > 280 chars → `400 hint_too_long`. Temp image kept ≤ 1 hour for the subsequent save call, then swept.

AI failures: `503 ai_unavailable` (connect), `504 ai_timeout` (> AI_TIMEOUT_S), `502 ai_bad_response` (schema fail after 1 repair retry). All preserve `temp_image_id` in `details` when possible so the UI can retry without re-upload.

cURL:
```bash
curl -X POST http://localhost:8000/api/v1/observations/analyze \
  -F "image=@leaf.jpg" -F "notes_hint=on the park path after rain"
```

## 3. Journal entries

### `POST /api/v1/journal-entries` → 201
```json
// request
{
  "temp_image_id": "tmp_01k7abc123",
  "ai_analysis": { /* analysis object from §2, or null if user saved without AI */ },
  "user_notes": "I watched two leaves for 2 minutes each. The sunny one felt warmer and looked slightly curled.",
  "experiment_done": true,
  "experiment_result": "Shaded leaf looked flatter. Sunny leaf edges curled a little."
}
// response 201
{
  "id": "entry_01k7xyz789",
  "title": "Outdoor note · 2026-10-09",
  "created_at": "2026-10-09T12:05:00Z",
  "image_url": "/media/entry_01k7xyz789/original.jpg",
  "thumbnail_url": "/media/entry_01k7xyz789/thumb_512.jpg",
  "analysis": { /* echoed, with model_id + analyzed_at */ },
  "user_notes": "…",
  "experiment_done": true,
  "experiment_result": "…"
}
```
Rules: `user_notes` required 1–2000 chars → else `400 notes_required`; `experiment_result` ≤ 2000 chars; `temp_image_id` must exist and be unclaimed → else `404 temp_image_expired`; `ai_analysis`, if present, must validate against §2 schema and its `model_id` must equal server `AI_MODEL_ID` → else `400 ai_model_mismatch`. Title is server-generated (`Outdoor note · YYYY-MM-DD`, local date of server). Atomic: file promote + DB insert in one transaction scope.

### `GET /api/v1/journal-entries` → 200
```json
{ "entries": [ { "id": "entry_01k7xyz789", "title": "Outdoor note · 2026-10-09", "created_at": "…", "thumbnail_url": "/media/…/thumb_512.jpg", "has_ai": true, "experiment_done": true } ],
  "total": 1 }
```
Newest first. No pagination in MVP (`total` included for future use; > 200 entries still returned — documented limit to add post-MVP).

### `GET /api/v1/journal-entries/{id}` → 200 | 404
Returns the full 201-shape object. Unknown id → `404 entry_not_found`.

### `DELETE /api/v1/journal-entries/{id}` → 204 | 404
Deletes DB rows + `data/uploads/{id}/` directory. Idempotent-second-call → `404 entry_not_found` (not 204).

## 4. Media

### `GET /media/{entry_or_tmp}/{file}` → 200 | 404
Serves `original.*` / `thumb_512.*` (JPEG/PNG/WebP as stored) with `Cache-Control: public, max-age=31536000, immutable` for entry files, `no-store` for `/media/tmp/*`. No directory listing. Path traversal (`..`) → `400 invalid_path`.

## 5. Types (shared)

```ts
// frontend/src/lib/api.ts (mirrors backend/app/schemas.py)
interface Experiment { title: string; steps: string[]; materials: string[]; safety_notes: string[]; estimated_minutes: number }
interface AIAnalysis { observed_features: string[]; cautious_explanation: string; uncertainty: string[]; experiment: Experiment; model_id: string; disclaimer: string; analyzed_at: string }
interface JournalEntry { id: string; title: string; created_at: string; image_url: string; thumbnail_url: string; analysis: AIAnalysis | null; user_notes: string; experiment_done: boolean; experiment_result: string | null }
interface ApiError { error: { code: string; message: string; details?: Record<string, unknown> }; request_id: string }
```
Constraints: `observed_features` 1–6 items ≤ 140 chars; `uncertainty` 1–4 items; `experiment.steps` 2–4 items; `estimated_minutes` ∈ {5,10,15}; `cautious_explanation` ≤ 800 chars. Backend enforces; frontend pre-validates save form only.

## 6. Error envelope (all 4xx/5xx)

```json
{ "error": { "code": "ai_unavailable", "message": "The AI helper is unavailable right now. Your photo is kept — retry or save your own observation.", "details": { "model_id": "gemma-4-26b-a4b-it" } }, "request_id": "req_abc123" }
```
Code table (message text is binding UI copy source):

| HTTP | `code` | When | UI action |
|------|--------|------|-----------|
| 400 | `no_image` / `invalid_image` / `hint_too_long` / `notes_required` / `ai_model_mismatch` / `invalid_path` | Client-correctable input | Inline message, no retry-as-is |
| 413 | `too_large` | File > 10 MB | "Choose a smaller photo (≤ 10 MB)" |
| 422 | `unusable_image` | Decode/dimension/content failure | "Try a different photo" |
| 404 | `entry_not_found` / `temp_image_expired` | Gone/expired | Back-link / re-upload |
| 502 | `ai_bad_response` | Model output failed schema twice | Retry analysis |
| 503 | `ai_unavailable` / `db_busy` | Downstream unavailable | Retry; save-without-AI offered for AI cases |
| 503 | `ai_busy` | Another analysis is already running (single inference slot) | Wait briefly, then retry; no photo is consumed server-side |
| 503 | `api_auth_error` / `api_quota_exhausted` | Provider rejected credentials (server-side config) / provider quota spent (neither is client-correctable, so 5xx per the envelope convention) | Same retry + save-without-AI behavior; `details` carries only `model_id`; never provider bodies, keys, traces, or paths |
| 504 | `ai_timeout` | Exceeded AI_TIMEOUT_S | Retry analysis |

Never return stack traces, file paths, model internals, or secrets in `message`/`details`.

## 7. API acceptance

- [ ] Pact-style check: frontend `api.ts` types compile against example payloads in §§1–3; backend Pydantic rejects each negative case in §6 with the exact `code`.
- [ ] `POST analyze` with the §2 cURL returns either the 200 shape or a §6 error — never HTML, never a bare stack trace.
- [ ] Save → list → detail → delete round-trip passes with `request_id` present on any forced failure (revoke/limit a throwaway key, or simulate provider 429/timeout, to force `503`/`504`).

*Next: `DATABASE.md` for persistence behind these contracts.*
