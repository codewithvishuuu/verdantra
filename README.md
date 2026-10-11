# Verdantra 🌱 — AI-powered botanical field journal

> Photograph something outdoors → get a cautious AI reading with visible evidence, uncertainty notes, and one safe mini-experiment → record what *you* observed in your field journal.
> **Predictions are unverified. Your observations are the record that counts.**

## The problem

People notice interesting things outdoors — an unusual leaf, bark patterns, fungi after rain — but have no low-friction way to ask "what might this be?", try a tiny safe experiment, and keep a record, without being misled by overconfident AI.

## What Verdantra does

- **Photo-based observation** — upload or take a JPEG/PNG/WebP photo (≤ 10 MB); client and server both validate type, size, and decodability.
- **Visible evidence, not verdicts** — the AI lists short photo-grounded traits, a plain-language description, and explicit uncertainty. Species names are never stated as certain.
- **Safe experiments only** — one short, in-place observation activity per analysis (3–5 minutes, household items), with safety notes. No picking, tasting, touching, or damaging unidentified plants.
- **Uncertainty as a feature** — every AI panel carries an `AI PREDICTION — UNVERIFIED` badge, model ID, and timestamp, visually distinct from your `YOUR OBSERVATION — CONFIRMED BY YOU` notes.
- **Personal field journal** — save photo + frozen AI snapshot + your notes; list newest-first, revisit entries, delete anytime (deletion removes rows *and* image files).

## AI modes: online Gemini, offline Ollama — you choose explicitly

| Mode | Setting | What happens | Needs |
|---|---|---|---|
| **Online (default)** | `AI_PROVIDER=gemini` | Hosted `gemma-4-26b-a4b-it` via the Gemini API | `GEMINI_API_KEY`, internet |
| **Offline** | `AI_PROVIDER=ollama` | Local `gemma4:e2b` via Ollama at `http://localhost:11434` | Ollama running + pulled model, no key |

There is **no automatic switching**: each mode calls only its own backend, unknown values fail fast at startup, and switching modes requires restarting the backend. The journal UI shows which model produced each result and adjusts its privacy footer to the active provider.

> ⚠️ **Privacy warning (automatic and online modes): photos you analyze are sent to Google's Gemini API.** On the API Free tier, Google may use submitted content to improve its products, including human review. Analyze only your own non-sensitive, consented photos, and strip location EXIF before uploading (the server strips EXIF GPS automatically, but do not rely on that alone). In `ollama` mode, images never leave your machine.

## Technology stack

Verified from this repository (`backend/requirements.txt`, `frontend/package.json`):

- **Frontend** — React 18, TypeScript 5, Vite 5, Tailwind CSS 3 (hash-routed SPA: `/`, `/journal`, `/journal/:id`)
- **Backend** — Python 3.11+, FastAPI, Uvicorn (single worker), Pydantic v2, Pillow, `google-genai` SDK
- **Data** — SQLite (stdlib `sqlite3`, WAL mode, single file) + filesystem image store; no ORM, no external database
- **AI runtimes** — Google Gemini API (`gemma-4-26b-a4b-it`) and/or local Ollama (`gemma4:e2b`); all provider calls live behind one `AIService` interface
- **Tests** — pytest (mocked providers, no live calls in CI), `tsc --noEmit`, `vite build`

## Architecture and documents

Two-tier app: browser SPA → FastAPI (`/api/v1/*`, `/healthz`, `/media/*`) → SQLite file. Full design record lives in [`docs/`](docs/):

- [`docs/PRD.md`](docs/PRD.md) — goals, scope, acceptance criteria
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system structure, config, deployment
- [`docs/DESIGN.md`](docs/DESIGN.md) — botanical field-journal visual system
- [`docs/AI_SYSTEM.md`](docs/AI_SYSTEM.md) — model choice, prompts, safety policy
- [`docs/API.md`](docs/API.md) — exact request/response and error contracts
- [`docs/USER_FLOWS.md`](docs/USER_FLOWS.md) — end-to-end user journeys
- [`docs/DATABASE.md`](docs/DATABASE.md) — schema, transactions, backups
- [`docs/SECURITY.md`](docs/SECURITY.md) — secrets, validation, privacy controls
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — milestone build order

## Prerequisites

- **Python 3.11+** with `pip` (backend was built and tested with Python 3.11.9)
- **Node.js 20+** with `npm` (frontend was built with Node 24)
- **Git** (to clone)
- **Ollama** (only for offline mode) with ~5 GB free disk for the model
- A Google AI Studio API key (only for online mode; free tier works for trials)

## Local setup (Windows PowerShell)

```powershell
git clone https://github.com/codewithvishuuu/verdantra.git
cd verdantra
```

### Backend

```powershell
cd backend
py -3.11 -m pip install -r requirements.txt
Copy-Item ..\.env.example ..\.env -ErrorAction SilentlyContinue  # skip if you already have one
# Open the root .env in a text editor and set GEMINI_API_KEY to your own key (online mode).
# Never commit .env, paste keys into chat, or put keys in frontend code.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

The API listens on `http://localhost:8000`; `GET /healthz` reports app, database, and AI status honestly (`ok` / `degraded` / `unavailable` — never faked). If you use the `py` launcher with another default Python, substitute the interpreter that has the dependencies installed (e.g. `C:\...\Python311\python.exe -m uvicorn …`).

### Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

No frontend restart is needed when switching AI modes — only the backend restarts.

## Selecting online, offline, or default mode

The backend reads `AI_PROVIDER` from its process environment (`gemini` default). Stop the server with <kbd>Ctrl</kbd>+<kbd>C</kbd>, set the mode, restart:

```powershell
# Online (default): hosted Gemini, needs GEMINI_API_KEY
$env:AI_PROVIDER = "gemini"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# Offline: local Ollama, needs no key and makes no Google calls
$env:AI_PROVIDER = "ollama"
$env:OLLAMA_HOST = "http://localhost:11434"
$env:OLLAMA_MODEL = "gemma4:e2b"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Any other `AI_PROVIDER` value fails fast at startup instead of guessing.

### Offline model installation (only model supported by the code)

```powershell
ollama pull gemma4:e2b
ollama show gemma4:e2b     # confirm the vision/multimodal lines
ollama list                # confirm the model is present locally
```

Offline image-analysis quality on this hardware is unmeasured — verify with a real photo before trusting it, and do not claim production behavior.

## Testing

```powershell
cd backend
python -m pytest tests/ -q     # mocked providers only; makes no live API calls
```

```powershell
cd frontend
npx tsc --noEmit
npm run build
```

For latency measurement, `backend/bench/bench_providers.py` runs a repeatable same-image benchmark per provider (run it yourself with a live backend; it is not part of CI and makes real calls when executed).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `503 ai_unavailable` in Gemini mode | `GEMINI_API_KEY` missing from backend process env (the app does not auto-load it in every setup — export it or use `.env` loading) | Set `$env:GEMINI_API_KEY` (your own key, never shared), restart backend |
| Startup log `GEMINI_API_KEY not set` | Same as above | Same fix; the message names only the variable, never the value |
| `503 api_auth_error` | Key present but rejected (revoked, wrong project) | Regenerate the key in Google AI Studio |
| `503 api_quota_exhausted` / `429` | Quota/rate limit spent | Wait, check AI Studio usage/billing; do not retry in a loop |
| `503 ai_unavailable` in Ollama mode | Ollama not running or model missing | Start Ollama, `ollama pull gemma4:e2b`, `ollama list` to confirm |
| `503 ai_busy` | Another analysis already running (single inference slot) | Wait a moment and retry; your draft is preserved |
| `504 ai_timeout` | Model slower than the provisional timeout | Retry; see `docs/AI_SYSTEM.md` §7 (timeouts are provisional) |
| `400/413/422` image errors | Wrong type, over 10 MB, or undecodable/tiny image | Use a JPEG/PNG/WebP ≤ 10 MB, ≥ 64×64 px |
| `EADDRINUSE` on start | Port taken | Backend: `--port 8001`; frontend: `npm run dev -- --port 5174` |
| Analysis succeeds but looks wrong | Model uncertainty, not a bug report by itself | Check the uncertainty panel; never treat predictions as facts |

## Screenshots

> No UI screenshots are checked into the repository yet. To add them: capture **New Observation** (empty + with AI report), **Journal list** (with entries), and **Entry detail** at **1280px** desktop and **360px** mobile widths; save PNGs under `docs/screenshots/` (e.g. `new-observation-1280.png`); reference them from this section. Do not use real private photos or journal entries containing personal data.

## Privacy, limitations, and field safety

- **Data handling:** uploads are validated, EXIF GPS is stripped, images are re-encoded, temp files from unsaved analyses are swept within an hour, and deletion removes rows *and* files. See [`docs/SECURITY.md`](docs/SECURITY.md) and [`docs/DATABASE.md`](docs/DATABASE.md).
- **Free-tier reality:** online analysis transmits sanitized image bytes to Google under the terms quoted above. Offline mode keeps everything on your machine.
- **Cost posture:** no billing is enabled by this project; any spend cap is your own AI Studio setting. Per-request pricing is unverified here — check current official pricing before heavy use.
- **Honest limits:** single-user demo, no login, no sync; one analysis at a time; timeouts and latency figures are provisional (a single ~47 s sample was reported during manual testing, not a guarantee); model output may be wrong — the journal's uncertainty panels and badges exist for exactly this reason; no uptime, accuracy, or security certifications are claimed.
- **Field safety:** stay on paths, observe wildlife from a distance, never pick, taste, touch, or damage unknown plants, and get an adult's help when unsure. This app gives observations, not identifications or advice.

## Contributing

Issues and pull requests are welcome. Please: keep changes small and scoped; run the backend suite plus `tsc` and `vite build` before proposing; never commit secrets (`.env`), photos, SQLite data, `node_modules/`, or build output; keep the nine documents under [`docs/`](docs/) separate and update the one that owns your change; do not redesign the logo or the visual system without discussion.

## License

**No license file exists in this repository yet.** That means the project is *not* currently open for reuse under any terms — do not assume one. The maintainer still needs to choose and add a license (MIT is a common choice for projects like this); until then, all rights are reserved by default.
