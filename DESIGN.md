# Verdantra — Design Specification (DESIGN.md)

**Version:** 0.2.0 · **Date:** 2026-10-09 · **Status:** Pre-implementation, binding for MVP (hosted time-box re-baseline for M1–M5)
**Depends on:** `PRD.md` (scope, decisions D1–D6) · **Feeds:** `ARCHITECTURE.md`, `USER_FLOWS.md`, frontend build

## 1. Brand principle

Verdantra = calm, field-notebook honesty. The UI must feel like a well-kept nature journal: generous whitespace, readable serif-tinged headings (system serif stack, no webfont download in MVP to keep one-day budget), earthy neutrals, one leaf-green accent. Scientific caution is a visual feature: AI output and user observations must never look the same.

**Hard rule (from PRD): use the provided Verdantra logo as the visual identity. Do not redesign it without permission.**

## 2. Logo usage (asset-missing protocol)

Repo inspection on 2026-10-09 found **no logo file** in the working directory (empty folder). Therefore:

1. Create `assets/logo/` with:
   - `verdantra-logo.svg` (or `.png`) — **the provided file, dropped in verbatim once supplied. Do not trace, recolor, or redraw it.**
   - `LOGO_README.md` — records source filename, date received, approved clear-space/min-size, and "do not modify" notice.
2. Header lockup (binding): logo left (height 32px desktop / 28px mobile), wordmark "Verdantra" in system font next to it only if the provided logo is mark-only; if the provided logo already contains the wordmark, show the logo alone. No gradients, shadows, or recoloring applied to the logo asset itself.
3. Favicon: export from the provided logo at 32×32 and 180×180 (`frontend/public/favicon-32.png`, `apple-touch-icon.png`) once the source arrives. Until then, ship a neutral placeholder square in `--moss` with the letter "V" and file an explicit TODO referencing this section — never present the placeholder as the brand.
4. Implementer is forbidden from generating an AI replacement logo. If no logo is supplied by build start, the header shows the wordmark text "Verdantra" in `--ink` with a `<!-- TODO(DESIGN-§2): drop in provided logo -->` comment.

## 3. Design tokens (Tailwind theme)

Define once in `frontend/tailwind.config.js` `theme.extend.colors` + CSS variables. Values below are **app-chrome colors only** (not applied to the logo):

| Token | Value | Use |
|-------|-------|-----|
| `--paper` | `#FAF7F0` | Page background (warm paper) |
| `--card` | `#FFFFFF` | Cards, form surfaces |
| `--ink` | `#1E2A24` | Primary text |
| `--muted` | `#5C6B62` | Secondary text, hints |
| `--moss` | `#2F6B4F` | Primary accent (buttons, links, active states) |
| `--moss-dark` | `#234F3A` | Button hover |
| `--fern` | `#E3EDE5` | Subtle tint behind AI-prediction panels |
| `--clay` | `#F3E8D3` | Tint behind user-observation panels |
| `--amber` | `#B7791F` | Uncertainty / caution badges, warnings |
| `--danger` | `#B3261E` | Destructive actions, errors |
| `--line` | `#E2DDD2` | Borders, dividers |
| Radius | `12px` cards, `8px` inputs/buttons | — |
| Type | Headings: `Georgia, 'Times New Roman', serif`; Body/UI: `system-ui, -apple-system, Segoe UI, Roboto, sans-serif` | No webfont fetch in MVP |

Dark mode: deferred (documented non-goal). Ensure contrast on light theme meets §6.

## 4. Prediction-vs-observation language (binding copy + badges)

This is a safety requirement, not decoration. Implement exactly:

- **AI output container:** light `--fern` background, 1px `--moss` left border (4px), header row with badge:
  - Badge: `AI PREDICTION — UNVERIFIED` (uppercase, `--moss` solid bg, white text, `text-xs font-semibold tracking-wide rounded-full px-2.5 py-0.5`).
  - Subline (always present): `"What the model sees in this photo. May be wrong — confirm outdoors before trusting it."` plus `Model: {model_id} · {timestamp}` in muted text.
- **User observation container:** light `--clay` background, 1px `--amber`-ish left border (`#D9A441`), header badge:
  - Badge: `YOUR OBSERVATION — CONFIRMED BY YOU` (`--ink` solid bg, white text, same shape).
  - Subline: `"What you did and saw. This is the record that counts."`
- Never place AI text inside the user container or vice versa. On the analyze screen the AI panel is read-only; the user textarea is empty by default (no AI-prefilled text).
- Uncertainty list renders as amber `⚠ {item}` lines under the explanation. Safety notes render as a bordered callout with `SAFETY` label.

## 5. Layout and screens (MVP, 4 screens + states)

Mobile-first, max content width `max-w-3xl mx-auto px-4`. Header (sticky): logo lockup left, nav (`New observation`, `Journal`) right, `GET /healthz` dot (green/amber/grey) with title tooltip. Footer: "Photos you analyze are sent to Google's Gemini API (Free tier: content may be used to improve Google products, incl. human review — your own non-sensitive photos only) · Predictions are unverified · Be safe outdoors · No foraging/medical advice" + docs links. Provider variants (same badges, same safety copy): `ollama` mode shows the on-device disclosure (nothing sent to Google); `auto` mode shows the try-hosted-first disclosure with the same Free-tier terms.

1. **New observation (`/`)** — upload card (drag-drop + file input + camera capture), preview thumbnail, client validation messages inline, `Analyze photo` button (disabled until valid image + not loading), loading skeleton ("Examining visible evidence… this can take a minute or more; provisional 150 s timeout"), then AI panel (§4) + observation form (textarea 1–2000 chars with live count, `I tried the experiment` checkbox, result textarea optional) + `Save to journal` button.
2. **Journal list (`/journal`)** — newest-first cards: thumbnail, auto-title (`Outdoor note · {date}`), date, badges (has-AI / experiment-done), empty state illustration (CSS only) + "Make your first observation" CTA.
3. **Entry detail (`/journal/:id`)** — full image, AI panel (§4, read-only, with model + timestamp), user panel (§4), delete button (confirm dialog), back link.
4. **Error/empty/offline states** — every API failure shows card with `error.message` verbatim + `Retry` button + `request_id` in muted monospace for bug reports. AI outage shows amber panel: "The AI helper is unavailable right now. Your photo is kept — you can still write and save your own observation." (Triggers include `ai_unavailable`, `api_auth_error`, `api_quota_exhausted`.) (Save-without-AI is allowed; `ai_analysis` nullable — matches `DATABASE.md`.)

## 6. Accessibility (WCAG 2.2 AA intent, testable)

- Semantic landmarks (`header/main/nav/footer`), one `h1` per screen, label every input (`<label for>`), error text with `role="alert"` and `aria-describedby`.
- Keyboard: all actions reachable by Tab, visible `:focus-visible` outline (2px `--moss`, offset 2px), no keyboard traps, confirm dialog traps focus and returns focus on close.
- Contrast: body text `--ink` on `--paper`/`--card` ≥ 4.5:1; `--moss` (#2F6B4F) on white ≈ 5.9:1 for button text — verify with a contrast tool during build and record result in PR.
- Images: every photo `<img alt="{user-provided title or 'Outdoor photo for journal entry'}">`; decorative icons `aria-hidden`.
- Reduced motion: `@media (prefers-reduced-motion: reduce)` disables transitions/animations.
- Touch: hit targets ≥ 44×44px; camera input works on mobile Safari/Chrome.

## 7. Responsive behavior

- `<640px`: single column, stacked panels (AI panel above user form), full-width buttons.
- `≥768px`: detail screen uses two-column (`AI prediction` | `Your observation`) grid; list uses 2-col card grid.
- Images: stored original + `thumb_512` variant (backend-generated at upload, see `ARCHITECTURE.md`); frontend uses `srcset` thumbnail in list, full in detail (lazy-load list images).

## 8. What is explicitly NOT designed in MVP

No dark mode, no map view, no charts, no avatars, no markdown editor (plain textarea only), no rich-text AI rendering (paragraphs + bullet lists only), no animations beyond 150ms ease transitions, no custom icon set (inline SVG, max 6 icons: upload, camera, leaf, alert, check, trash).

## 9. Design acceptance checklist

- [ ] Logo slot follows §2 (provided file verbatim or documented placeholder + TODO).
- [ ] Tokens implemented once in Tailwind config; no hardcoded hex elsewhere (grep check).
- [ ] AI vs user panels match §4 badges/copy on both analyze and detail screens.
- [ ] All four screens + error/empty states render at 360px and 1280px without horizontal scroll.
- [ ] Accessibility items in §6 verified by keyboard-only pass + contrast tool reading recorded.

*Next: `ARCHITECTURE.md` for system structure implementing this design.*
