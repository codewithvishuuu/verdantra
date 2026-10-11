# Verdantra — Security, Privacy & Validation (SECURITY.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Binding for MVP (hosted time-box re-baseline for M1–M5)
**Depends on:** `PRD.md` (NFR-7, §9), `ARCHITECTURE.md`, `API.md` §6, `AI_SYSTEM.md` §§6–7

Threat posture: single-tenant demo on one host, no login (PRD D3), time-boxed hosted AI in MVP (M1–M5). Controls below are the minimum for internet exposure; anything marked DEFERRED must not be silently skipped if the deploy becomes multi-user.

## 1. Scope and assumptions

- In scope: secrets handling, image upload validation, API input validation, error hygiene, CORS/TLS, filesystem safety, privacy (photos, EXIF, logs), dependency hygiene, pre-push audit.
- Out of MVP scope (explicitly deferred, not forgotten): authentication/accounts, rate-limiting service, WAF, malware scanning of uploads, NSFW classifier (mitigated by single-user + delete; future note: ShieldGemma-2 evaluation deferred), automated backups, SIEM/log aggregation, penetration test.
- Claim discipline: no "secure/audited/compliant" statements in docs or UI. This file describes controls, not certifications.

## 2. Secrets — zero in source control (blocking rule)

1. All config via environment (`ARCHITECTURE.md` §4). Code must read `os.environ` with no hardcoded keys, tokens, passwords, or salts. `.env` (if used locally) is git-ignored and never committed, even redacted.
2. Commit `.env.example` with placeholder-only values (`GEMINI_API_KEY=replace_with_your_key`, no real hostnames/keys). CI/review rejects any diff adding `*.env`, `*_key*`, `*token*`, `BEGIN PRIVATE KEY`, `sk-`, `hf_`, `AIza`.
3. HF gated-repo token (only if a local TransformersAdapter path is ever reactivated — not active in the hosted time-box): env `HF_TOKEN`, mounted at runtime, never logged, never returned in API responses.
4. Pre-push gate (run manually in MVP, automate post-MVP): `git status --short`, `git diff --check`, `git grep -nE 'sk-|hf_|AIza|BEGIN PRIVATE KEY|AKIA|mongodb\+srv://|xox[bap]-' -- . || true`, confirm `.env` absent via `git ls-files | grep -x '.env'` returning nothing.
5. `GEMINI_API_KEY` (active while the hosted path is): env-only, startup presence-check without printing, never logged or returned in API responses. Rotate by replacing the value + restarting. A revoked/invalid key must surface as `api_auth_error`, never bypassed or retried silently.

## 3. Input validation (server is authoritative; client checks are UX only)

- `image`: presence → magic-byte sniff (JPEG `FFD8FF`, PNG `89504E47`, WebP `RIFF....WEBP`) via Pillow `Image.open().verify()` + format allowlist; extension alone is never trusted. Size ≤ `MAX_IMAGE_MB` (default 10 MB) enforced on streamed read (reject-early with 413). Dimensions 64×64 min, 4096px longest-edge max (downscale with `Image.LANCZOS`, preserve aspect). Failures map to `API.md` §6 codes; temp file deleted on any failure.
- `notes_hint`: strip control chars, truncate-check ≤ 280 chars (400 if over). `user_notes`/`experiment_result`: 1–2000 / 0–2000 chars, reject null bytes, normalize `\r\n` → `\n`, store verbatim otherwise (no HTML sanitization needed — frontend renders with `textContent`/React escaping, never `dangerouslySetInnerHTML`; add a lint comment to enforce).
- `id`/`temp_image_id`: allowlist `^[A-Za-z0-9_-]{1,64}$`; anything else → 400. All DB access parameterized (`?` placeholders only — string-interpolated SQL is a blocking review finding).
- JSON bodies: Pydantic strict models from `API.md` §5 (extra fields ignored, wrong types → 422 via FastAPI handler remapped into the standard envelope).

## 4. Image handling security + privacy

1. **Re-encode every upload** (JPEG q85 / PNG optimize / WebP q85) and **strip all EXIF** including GPS (`Image.ExifTags`, `piexif`-equivalent via Pillow `getexif().clear()` + save without exif block). Log only `exif_stripped: true`, never tag contents.
2. Store outside web root logic: served read-only via `/media/*` handler with allowlisted extensions, `Content-Type` sniffed from bytes, `X-Content-Type-Options: nosniff`, no directory listing, `..` rejected (400).
3. No image bytes in logs, errors, or analytics. Outbound transmission only to the Google Gemini API endpoint, carrying EXIF-stripped/re-encoded bytes (raw originals never leave disk). In `ollama` offline mode nothing leaves the host at all (localhost inference, no key). Document in UI footer per the §5 wording below.
4. Deletion is real deletion: `DELETE` removes files from disk (§4 of `DATABASE.md`); no soft-delete, no trash retention in MVP.
5. Upload abuse mitigations for MVP: 10 MB cap, dimension caps, temp sweep (1h), single-worker write path. Explicitly deferred: per-IP rate limits, virus scan, content-moderation classifier — acceptable only because MVP is single-tenant demo; re-evaluate before any shared/public deploy.

## 5. Privacy commitments (user-facing, must appear in README + footer)

- No accounts, no tracking pixels, no third-party analytics/CDN calls in MVP (system font stack, no webfonts — `DESIGN.md` §3).
- No location collection (no GPS columns by design — `DATABASE.md` §6). Optional context hint is free text; warn users not to type personal data (placeholder text: "Optional context — don't include names or addresses").
- Retention: temp images ≤ 1 hour; journal entries until the user deletes them. No backups leave the host automatically in MVP.
- ⚠️ **Binding Free-tier limitation (prominent):** photos chosen for analysis leave this host as sanitized copies sent to Google's Gemini API. On the current Free tier, Google may use submitted content to improve its products, including human review. Analyze only your own non-sensitive, consented photos. **$0-spend posture: billing is not enabled and no spend cap exists; any future paid-tier cap is unresolved and needs explicit approval.** No paid-tier privacy applies unless a tier change is independently confirmed.
- Disclosure: `README.md` §7 states exactly where photos live (`data/uploads/`), that EXIF GPS is stripped, and how to delete (in-app delete + manual `rm -rf data/uploads/{id}` fallback). Provider is fixed at startup: `gemini` sends sanitized copies to Google's API, `ollama` keeps everything local — restart to switch, never both in one process.

## 6. Transport, CORS, headers, files

- TLS in prod (Caddy/Nginx + Let's Encrypt; no TLS termination in FastAPI itself). Dev localhost may use HTTP — document the difference in deploy notes, never ship prod on bare HTTP.
- CORS: exact-origin allowlist from `CORS_ORIGINS` (no `*`, no reflected `Origin`, no credentials in MVP). Security headers via reverse proxy: `Strict-Transport-Security`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(self)` (camera only where needed).
- `.gitignore` (binding contents — already created during setup; verify with `git check-ignore -v .env` before the first commit once git is initialized): `.env`, `data/*.db*`, `data/uploads/`, `__pycache__/`, `*.pyc`, `node_modules/`, `frontend/dist/`, `.venv/`, `*.log`. `data/.gitkeep` is the only tracked file under `data/`.

## 7. Dependencies and supply chain (one-day proportionate)

- Pin versions in `backend/requirements.txt` (`fastapi==…`, `uvicorn==…`, `python-multipart==…`, `pillow==…`, `google-genai==2.23.0`) and `frontend/package.json` (react, vite, tailwind) at build time; record versions in the build PR. No new runtime dependency may be added during MVP without updating `ARCHITECTURE.md` + this file.
- Pre-deploy check: `pip audit` (or `pip index` + manual CVE glance if offline) and `npm audit --omit=dev`; fix criticals or document accepted risk in the PR. No committed lockfile bypasses.

## 8. Error hygiene

Standard envelope only (`API.md` §6). Never leak tracebacks, SQL, paths, env values, or model internals. Log full traceback server-side with `request_id`; return only `code/message/details/request_id`. Frontend shows `message` + `Retry` + muted `request_id`.

## 9. Security acceptance (pre-merge checklist)

- [ ] `git ls-files` shows no `.env`, no `*.db`, no uploads; `.env.example` has placeholders only.
- [ ] Upload of `.exe`/polyglot/25 MB/1×1 px image rejected with the exact `API.md` codes; EXIF GPS verified stripped (inspect saved file with `exiftool` or Pillow — record tool + result in PR).
- [ ] `..` media path → 400; interpolated-SQL grep finds nothing; `dangerouslySetInnerHTML` grep finds nothing.
- [ ] Forced provider outage → honest 503/504 path (no fallback fabrication); headers/CORS verified against §6.
- [ ] `GEMINI_API_KEY` absent from repo (`grep AIza` clean); spend-cap/quota state recorded; free-tier limitation acknowledged.

*Next: `IMPLEMENTATION_PLAN.md` for the one-day build order using these controls.*
