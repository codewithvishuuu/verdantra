# Verdantra — AI System (AI_SYSTEM.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP (hosted time-box re-baseline for M1–M5; permanent adoption gated on Phase 5)
**Depends on:** `PRD.md` (D1/D2), `ARCHITECTURE.md` §3 · **Feeds:** backend `app/services/ai_service.py`, `API.md` §3.1

> Safety note: this model gives nature observations, not identifications. It must never present guesses as facts and must never advise consuming, touching, or approaching anything.

## 1. Model selection (verified, narrow)

- **MVP model (time-boxed M1–M5): `gemma-4-26b-a4b-it` via the Gemini API (hosted).**
  - Why: instruction-tuned Gemma 4 MoE (25.2B total, 3.8B active per token), text + image → text, 256K context. Chosen after local E2B inference proved impractical on the 7.8 GB CPU-only builder machine. Permanent adoption remains gated on Phase 5 verification.
  - Sources verified: supported-model list + image-input example at `ai.google.dev/gemma/docs/core/gemma_on_gemini_api`; `google-genai` 2.23.0 SDK signatures verified locally (`Client(api_key=…)`, `models.generate_content`, `Part.from_bytes`, `GenerateContentConfig` with `response_mime_type`/`response_schema`/`thinking_config`). Links belong in `README.md`, not hardcoded in code.
- **Prior local path (retained as documented alternative, not active):** `google/gemma-4-E2B-it` via Ollama tag `gemma4:e2b`, with `gemma4:e4b` fallback. Reactivate only by a new coordinated doc change + fresh verification.
- **What is NOT assumed:** per-request price for this model (exact official row unverified), per-model quota values for this key, latency distribution (one reported sample only), or any hosted-inference SLA. Silent substitution with another model family is forbidden.

## 2. Documented inference implementation + verification gate (Milestone 0, blocks build)

One active adapter behind one interface (env `AI_BACKEND=gemini`).

**GeminiAdapter (hosted Gemini API — active, time-boxed M1–M5):**

```python
from google import genai
from google.genai import types
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # env-only, never logged
response = client.models.generate_content(
    model="gemma-4-26b-a4b-it",
    contents=[types.Part.from_bytes(data=sanitized_bytes, mime_type=mime),
              SYSTEM_PROMPT],  # image-before-text modality order
    config=types.GenerateContentConfig(response_mime_type="application/json"),
)
```

Verification gate: one owner-reported `SMOKE-PASS` (~47.4 s, single sample, not independently measured) using `smoke/gemma_api_smoke.py`; mandatory five-run latency log in M5 before any permanent decision. Record SDK version (2.23.0), model ID, image bytes, latency, date per run.
The newer Interactions API (`client.interactions.create()`) is **deferred**: `generate_content` is legacy but officially fully supported, and it is the verified path. Migration would change request/response shapes and needs its own verification — tracked post-MVP.

**OllamaAdapter (local Ollama — offline mode, opt-in via `AI_PROVIDER=ollama`):**
same `AIService` contract, `POST {OLLAMA_HOST}/api/chat` with `{model, stream:false, format:"json", messages:[system, user+images[]]}` (base64 image array per `docs.ollama.com/capabilities/vision`; `gemma4:e2b` carries the registry `vision` tag with a bundled projector). No key, no Google traffic by construction — the adapter cannot build a cloud request, and unknown providers fail fast instead of rerouting. **Live image analysis is NOT verified:** neither a runtime nor the model was present in this environment, so confirm with a real photo (`ollama pull gemma4:e2b`, one-image smoke) before claiming offline vision works.

**Backend call contract (Gemini API):** send EXIF-stripped/re-encoded bytes (never raw originals) as `Part.from_bytes` with the §4 system prompt, `response_mime_type="application/json"`, client timeout `AI_TIMEOUT_S` (default 120, provisional pending the five-run log). Response text must parse as JSON matching `API.md` §3.1; else one repair retry, then `502 ai_bad_response`.

> Retired: automatic hosted→local failover (`AI_PROVIDER=auto`) was removed. Choose
> the provider explicitly at startup and restart to switch — explicit modes never
> reroute, and unknown values fail fast instead of guessing.

## 3. Service interface (implement exactly)

```python
# backend/app/services/ai_service.py
class AIAnalysis(TypedDict):  # mirrors API.md §3.1 + DATABASE.md ai_analyses
    observed_features: list[str]
    cautious_explanation: str
    uncertainty: list[str]
    experiment: dict  # {title, steps[], materials[], safety_notes[], estimated_minutes}
    model_id: str
    disclaimer: str

class AIService(Protocol):
    model_id: str
    def analyze(self, image_path: str, hint: str | None) -> AIAnalysis: ...
    def ping(self) -> bool: ...   # for /healthz `ai` field
```

Rules: adapters may only return validated `AIAnalysis`; no raw model prose escapes the service; every returned object carries the exact `model_id` used; failures raise typed errors (`AITimeout`, `AIUnavailable`, `AIBadResponse`) mapped to `504/503/502` per `API.md` §6.

## 4. Prompt contract (binding text — do not improvise at runtime)

System prompt (sent every call — one shared constant, `SYSTEM_PROMPT`, used verbatim by
both adapters: Gemini appends the observer hint to it, Ollama sends it as the system
message, so both providers receive identical style, accuracy, and safety instructions
with zero request-format changes):

```
You are Verdantra Field Helper, a friendly outdoor-observation assistant.
Write for an ordinary beginner in plain everyday English a school student understands.
Say 'plant name' not 'botanical identification', 'colors' not 'a wide spectrum of colors',
'cannot tell' not 'cannot be assessed'.
STYLE (always follow):
- Use short sentences and simple common words.
- Write direct sentences like 'The visible stem looks dark'.
- If a science word is truly needed, explain it in plain words at once.
- Start with 2 or 3 short sentences describing the visible subject directly;
  no long paragraphs.
- Never repeat the same point twice; no introductions, no filler phrases.
- Never show internal reasoning or a step-by-step thinking process.
- Keep uncertainty short and specific to this photo; never repeat generic limitations.
- Do not cut useful observations or safety notes just to be brief.
ACCURACY (always follow):
- Analyze ONLY what is visibly evidenced in the attached photo.
- Never invent species names, measurements, locations, weather, or facts not visible.
- State visible facts plainly in observed_features; keep possibilities in the
  description and uncertainty only, marked with hedged words like 'appears',
  'may be', or 'consistent with'.
- Never infer plant hardiness, typical habitat, health, growing conditions,
  or common use from appearance alone.
- Never claim the user performed any experiment.
SAFETY (always follow):
- Suggest only safe outdoor observation with household materials,
  preferably observing the subject in place without disturbing it.
- Do not ask users to pick, collect, or handle leaves or plants unless clearly
  safe and genuinely necessary for the observation.
- No fire, chemicals, sharp tools, consumption, touching unknown plants or fungi,
  or approaching or disturbing animals.
- Never encourage tasting, ingesting, damaging, or handling an unidentified plant.
- No medical, foraging, or survival advice.
You MUST return strict JSON with exactly these keys:
{
  "observed_features": ["3 to 5 short visible traits"],
  "cautious_explanation": "One short paragraph (1 or 2 sentences) that adds meaning to the bullets: say what the traits together suggest, without restating their colors, shapes, or textures. Describe only visible details unless an inference is clearly labeled uncertain and genuinely useful. If nothing beyond the bullets is supported, keep it to one very short sentence.",
  "uncertainty": ["1 to 3 short items that genuinely matter for interpreting this photo;",
    " never state the obvious (e.g. that texture cannot be felt through a picture)",
    " unless it directly changes what the observation means"],
  "experiment": {"title": "a short descriptive title for a 3 to 5 minute watch-and-note activity",
    "steps": ["2 or 3 clear steps done by observing in place from a distance (a 4th only if truly needed)",
      " never pick, collect, touch, taste, or damage the plant"],
    "materials": ["minimal realistic items, e.g. paper, pencil"],
    "safety_notes": ["concise guidance stated once, not repeated across steps:",
      " stay on paths, watch from a distance, ask an adult for help with anything unsure"],
    "estimated_minutes": 5},
  "disclaimer": "AI prediction based only on this photo. May be wrong. Your own observation is the record that counts."
}
One experiment only, plain language suitable for beginners.
```

User message: optional `hint` (≤ 280 chars, user-supplied context such as "found near a puddle") + image. If image is unusable (blurry/dark/no natural subject detectable), the model is instructed to return `observed_features: ["Image does not show a clear outdoor subject"]` with explanation stating the limitation — backend still validates the schema and the UI shows it honestly rather than erroring, unless the image fails technical validation first (`SECURITY.md` §4).

JSON output is additionally constrained with `response_mime_type="application/json"`; server-side Pydantic validation (§5) remains authoritative, with one repair retry allowed before `502`.

## 5. Uncertainty, honesty, and prediction-vs-observation discipline

- Every analysis response includes non-empty `uncertainty[]` and the fixed `disclaimer`; backend rejects responses missing them (`502`).
- UI copy rule: AI text always under `AI PREDICTION — UNVERIFIED` badge with `Model: {model_id} · {timestamp}`; user text always under `YOUR OBSERVATION — CONFIRMED BY YOU`. The words "identify/confirm/diagnose" are forbidden in AI copy; allowed hedges: "appears", "may be", "consistent with", "cannot tell from this photo".
- No numeric fields (size, count, pH, temperature) are ever generated by the model. If the user types numbers in their notes, they are stored verbatim and labeled as user-supplied.
- Illustrative examples in docs/PRs must be labeled `EXAMPLE — not a real model result`. Do not paste real user photos into docs.

## 6. Safety policy (refusals + safe completion)

Refuse-or-redirect (return a safe completion that still matches the JSON schema, with explanation stating the refusal reason) when:

1. The request asks for edibility/medicinal use, foraging, dosage, or survival advice.
2. The experiment would require fire, chemicals, sharp tools, electricity, consumption, touching unknown plants/fungi, or approaching/disturbing animals.
3. The image appears to show a person (especially a child), a private interior, a screen, or text documents — respond that Verdantra only discusses outdoor natural subjects and suggest retaking the photo outdoors.
4. The user asks for a definitive species ID, age, or measurement from the photo alone — give only visible traits + uncertainty + a safe observation experiment (e.g., "sketch the leaf shape and note where light falls").

All refusals are logged (without image bytes) with `error_code: ai_safety_refusal` only if the request is blocked entirely; safe-completion redirects are normal `200` responses whose `cautious_explanation` states the boundary in plain language.

## 7. Privacy, image validation, errors, costs, hardware (AI-specific)

- **Privacy:** sanitized image bytes (EXIF-stripped/re-encoded — never raw originals) are sent to Google's Gemini API. Temp images from un-saved analyses are deleted within 1 hour (sweep job or on next request — document choice in code comment). ⚠️ **Binding Free-tier limitation:** on the current Free tier, Google may use submitted content to improve its products, including human review. Analyze only your own non-sensitive, consented photos. No paid-tier privacy applies unless a tier change is independently confirmed.
- **Validation:** max 10 MB, JPEG/PNG/WebP magic bytes, 64×64 min, 4096px longest-edge max (downscale server-side). Strip-before-transmit order is mandatory for hosted sends. NSFW/explicit-content classifier is **out of MVP** — mitigation is single-user local use + delete control + documented future ShieldGemma-2 note (deferred).
- **Errors:** `504 ai_timeout` (>AI_TIMEOUT_S, default 120 provisional), `503 api_auth_error` / `api_quota_exhausted` / `ai_unavailable`, `502 ai_bad_response` (schema fail twice), each with retry copy; frontend preserves the photo and user draft across retries.
- **Costs:** metered per-request billing. Exact official 26B row unverified (third-party aggregators suggest ~$0.04–0.13 input / $0.20–0.40 output per 1M — unverified proxies, not quotes). **$0-spend posture: billing is not enabled and no payment method is configured; any future spend cap is unresolved and needs explicit approval.** Thinking tokens bill as output — cap thinking and `max_output_tokens`.
- **Hardware/latency:** no local model runs; the app host needs only the app tier. One owner-reported sample: ~47.4 s (not independently measured). No p50/SLA claim until the five-run log (M5). Timeouts 120/150/180 s are provisional pending that log.
- **Quota (screenshot-observed, not guarantees):** project `gemma-4`, Free tier, Gemma 4 26B limits shown as 30 RPM / 16K TPM / 14.4K RPD with current usage 1 RPM / 312 TPM / 1 RPD at screenshot time. Re-check live on any 429.
- **Performance bounds (all provisional, pending measurement):** provider payloads are capped by `TRANSMIT_MAX_EDGE` (default `2048` px longest edge) and `TRANSMIT_JPEG_QUALITY` (default `82`); already-suitable JPEGs pass through byte-identical, and stored originals/thumbnails are unaffected — so fine detail beyond 2048 px is unavailable to the model, a tuning trade-off, not a quality claim. Hosted output is capped by `GEMINI_MAX_OUTPUT_TOKENS` (default `1024`); over-long valid analyses would 502 honestly rather than save truncated. Ollama sends `num_ctx` (default `4096`), `num_predict` (default `1024`), and `keep_alive` (default `5m`): small context because one image + prompt needs far less than 128K, capped output mirroring the hosted bound, and default residency with never more than one model loaded (longer residency on 8 GB RAM was deliberately not chosen).
- **Offline mode:** `AI_PROVIDER=ollama` sends nothing off-host (localhost inference, no key, no billing); same validation, timeouts, and 503/504/502 codes. Provider errors surface honestly — missing model or dead server yields `ai_unavailable` with save-without-AI preserved, never a silent cloud fallback.
- **Load discipline (8 GB CPU-only host):** one analysis at a time — a concurrent analyze fails fast with `503 ai_busy` instead of stacking full-model inferences (`--workers 1` assumed; a multi-worker deploy would need a shared slot). `OLLAMA_NUM_CTX` stays 4096 (a 2048 budget risks overflow: image ≤1120 + prompt ~700 + output ≤1024 tokens worst case) and `OLLAMA_NUM_PREDICT` stays 1024 (truncation risk unmeasured) until live quality tests justify less. `OLLAMA_KEEP_ALIVE` stays `5m`: resident model speeds consecutive requests but holds ~4.5 GB; shorten only with idle-RAM evidence. `OLLAMA_NUM_THREAD` (default 0 = server default) is the fan lever: set 2–4 to trade speed for thermals, only after measuring.

## 8. Verification log (fill in Milestone 0 — build is blocked while empty)

| Date | Backend | Model tag / repo | Host specs | Smoke image | Latency | Result |
|------|---------|------------------|------------|-------------|---------|--------|
| 2026-10-09 | gemini (reported) | `gemma-4-26b-a4b-it` via Gemini API, SDK 2.23.0 | builder PC, 7.8 GB RAM, CPU-only (no local inference) | owner-supplied outdoor photo (disposition unconfirmed — neither deleted nor retained is claimed) | ~47.4 s (owner-reported, single sample, not independently measured) | PASS (reported); five-run confirmation pending |

Active backend for MVP (time-boxed M1–M5, proposed values): `AI_BACKEND=gemini` · `AI_MODEL_ID=gemma-4-26b-a4b-it` (must match `ARCHITECTURE.md` §4 and every stored analysis row once applied).

*Next: `USER_FLOWS.md` for end-to-end behavior, `API.md` for exact contracts.*
