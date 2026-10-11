"""AIService boundary (AI_SYSTEM.md sections 2-3, ARCHITECTURE.md section 3).

`services/ai_service.py` is the ONLY module that talks to the model endpoint.
Routes never import the SDK. Timeouts use the configured AI_TIMEOUT_S via a
worker thread (stdlib only) — the value stays provisional per the docs.
No keys, prompts, image bytes, or raw provider text ever reach logs.
"""

import base64
import concurrent.futures
import datetime
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from app import schemas

SYSTEM_PROMPT = (
    "You are Verdantra Field Helper, a friendly outdoor-observation assistant.\n"
    "Write for an ordinary beginner in plain everyday English a school student understands.\n"
    "Say 'plant name' not 'botanical identification', 'colors' not 'a wide spectrum of colors',\n"
    "'cannot tell' not 'cannot be assessed'.\n"
    "STYLE (always follow):\n"
    "- Use short sentences and simple common words.\n"
    "- Write direct sentences like 'The visible stem looks dark'.\n"
    "- If a science word is truly needed, explain it in plain words at once.\n"
    "- Start with 2 or 3 short sentences describing the visible subject directly;\n"
    "  no long paragraphs.\n"
    "- Never repeat the same point twice; no introductions, no filler phrases.\n"
    "- Never show internal reasoning or a step-by-step thinking process.\n"
    "- Keep uncertainty short and specific to this photo; never repeat generic limitations.\n"
    "- Do not cut useful observations or safety notes just to be brief.\n"
    "ACCURACY (always follow):\n"
    "- Analyze ONLY what is visibly evidenced in the attached photo.\n"
    "- Never invent species names, measurements, locations, weather, or facts not visible.\n"
    "- State visible facts plainly in observed_features; keep possibilities in the\n"
    "  description and uncertainty only, marked with hedged words like 'appears',\n"
    "  'may be', or 'consistent with'.\n"
    "- Never infer plant hardiness, typical habitat, health, growing conditions,\n"
    "  or common use from appearance alone.\n"
    "- Never claim the user performed any experiment.\n"
    "SAFETY (always follow):\n"
    "- Suggest only safe outdoor observation with household materials,\n"
    "  preferably observing the subject in place without disturbing it.\n"
    "- Do not ask users to pick, collect, or handle leaves or plants unless clearly\n"
    "  safe and genuinely necessary for the observation.\n"
    "- No fire, chemicals, sharp tools, consumption, touching unknown plants or fungi,\n"
    "  or approaching or disturbing animals.\n"
    "- Never encourage tasting, ingesting, damaging, or handling an unidentified plant.\n"
    "- No medical, foraging, or survival advice.\n"
    "You MUST return strict JSON with exactly these keys:\n"
    "{\n"
    '  "observed_features": ["3 to 5 short visible traits"],\n'
    '  "cautious_explanation": "One short paragraph (1 or 2 sentences) that adds meaning to the bullets: say what the traits together suggest, without restating their colors, shapes, or textures. Describe only visible details unless an inference is clearly labeled uncertain and genuinely useful. If nothing beyond the bullets is supported, keep it to one very short sentence.",\n'
    '  "uncertainty": ["1 to 3 short items that genuinely matter for interpreting this photo;",\n'
    '    " never state the obvious (e.g. that texture cannot be felt through a picture)",\n'
    '    " unless it directly changes what the observation means"],\n'
    '  "experiment": {"title": "a short descriptive title for a 3 to 5 minute watch-and-note activity",\n'
    '    "steps": ["2 or 3 clear steps done by observing in place from a distance (a 4th only if truly needed)",\n'
    '      " never pick, collect, touch, taste, or damage the plant"],\n'
    '    "materials": ["minimal realistic items, e.g. paper, pencil"],\n'
    '    "safety_notes": ["concise guidance stated once, not repeated across steps:",\n'
    '      " stay on paths, watch from a distance, ask an adult for help with anything unsure"],\n'
    '    "estimated_minutes": 5},\n'
    '  "disclaimer": "AI prediction based only on this photo. May be wrong. '
    'Your own observation is the record that counts."\n'
    "}\n"
    "One experiment only, plain language suitable for beginners."
)

REPAIR_PROMPT = (
    "Your previous output failed validation: {error}. "
    "Return ONLY the corrected strict JSON object with exactly the required keys."
)


class AIError(Exception):
    code = "ai_unavailable"
    status = 503

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


class AITimeout(AIError):
    code = "ai_timeout"
    status = 504


class AIAuthError(AIError):
    code = "api_auth_error"
    status = 503


class AIQuotaError(AIError):
    code = "api_quota_exhausted"
    status = 503


class AIBadResponse(AIError):
    code = "ai_bad_response"
    status = 502


class AIService(Protocol):
    model_id: str

    def analyze(self, image_bytes: bytes, mime: str, hint: str | None) -> dict:
        """Return a validated AIAnalysis dict (raises AIError subclasses)."""
        ...

    def ping(self) -> bool:
        """Configured-reachability only: True iff credentials are present.

        Full reachability is proven per real call; failures surface as
        503/504 there. Ping itself makes no network calls and costs nothing.
        """
        ...


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_analysis(raw_text: str, model_id: str) -> dict:
    try:
        payload = json.loads(raw_text)
    except Exception as exc:
        raise AIBadResponse("unparseable model output: %s" % type(exc).__name__)
    if not isinstance(payload, dict):
        raise AIBadResponse("model output is not a JSON object")
    payload = dict(payload)
    payload["model_id"] = model_id
    if "disclaimer" not in payload:
        payload["disclaimer"] = (
            "AI prediction based only on this photo. May be wrong. "
            "Your own observation is the record that counts."
        )
    try:
        validated = schemas.AIAnalysis.model_validate(payload)
    except Exception as exc:
        raise AIBadResponse("schema validation failed: %s" % type(exc).__name__)
    out = validated.model_dump()
    out["analyzed_at"] = _utcnow()
    return out


def _classify_provider_error(exc: Exception) -> AIError:
    text = ("%s %s" % (type(exc).__name__, str(exc))).lower()
    if "401" in text or "unauthenticated" in text or "api key" in text or "api_key" in text:
        return AIAuthError(type(exc).__name__)
    if "429" in text or "resource_exhausted" in text or "quota" in text:
        return AIQuotaError(type(exc).__name__)
    return AIError("%s (no bytes, prompts, or keys logged)" % type(exc).__name__)


def _run_with_timeout(fn: Callable[[], str], timeout_s: int) -> str:
    """Enforce the provisional AI timeout with stdlib only (both adapters)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise AITimeout("provider call exceeded %ss" % timeout_s) from exc


class GeminiAdapter:
    """Hosted Gemini API adapter (time-boxed M1–M5). Interactions API deferred."""

    def __init__(self, model_id: str, api_key: str, timeout_s: int = 120,
                 max_output_tokens: int = 1024,
                 caller: Callable[..., str] | None = None) -> None:
        self.model_id = model_id
        self._api_key = api_key  # held in memory only; never logged/printed/returned
        self._timeout_s = timeout_s
        self._max_output_tokens = max_output_tokens  # bounds cost + latency
        self._caller = caller  # test seam: (image_bytes, mime, prompt_text) -> raw text

    def ping(self) -> bool:
        return bool(self._api_key)

    def _direct_call(self, image_bytes: bytes, mime: str, prompt_text: str) -> str:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self.model_id,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime),
                      prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=self._max_output_tokens),
        )
        return response.text or ""

    def _call_with_timeout(self, image_bytes: bytes, mime: str, prompt_text: str) -> str:
        fn = self._caller or self._direct_call
        return _run_with_timeout(
            lambda: fn(image_bytes, mime, prompt_text), self._timeout_s)

    def analyze(self, image_bytes: bytes, mime: str, hint: str | None) -> dict:
        if not self._api_key and self._caller is None:
            raise AIError("no credentials configured")
        prompt = SYSTEM_PROMPT if not hint else SYSTEM_PROMPT + "\nObserver context: " + hint
        try:
            raw = self._call_with_timeout(image_bytes, mime, prompt)
        except AIError:
            raise
        except Exception as exc:  # SDK/network surface; classify, never leak
            raise _classify_provider_error(exc) from exc
        try:
            return _parse_analysis(raw, self.model_id)
        except AIBadResponse as first:
            repair = REPAIR_PROMPT.format(error=first.detail)
            try:
                raw2 = self._call_with_timeout(image_bytes, mime, repair)
            except AIError:
                raise
            except Exception as exc:
                raise _classify_provider_error(exc) from exc
            return _parse_analysis(raw2, self.model_id)  # raises AIBadResponse if still bad


class OllamaAdapter:
    """Local Ollama adapter (offline mode). Same AIService contract as Gemini.

    Uses only the local Ollama HTTP API; never imports google-genai and never
    contacts Google, so there is nothing to leak and no billing possible.
    Image support follows the official Ollama vision capability
    (POST {host}/api/chat with an `images` array of base64 data).
    Live image analysis is NOT verified here — see AI_SYSTEM.md.
    """

    def __init__(self, model_id: str = "gemma4:e2b",
                 host: str = "http://localhost:11434", timeout_s: int = 120,
                 num_ctx: int = 4096, num_predict: int = 1024,
                 keep_alive: str = "5m", num_thread: int = 0,
                 caller: Callable[..., str] | None = None) -> None:
        self.model_id = model_id
        self._host = host.rstrip("/")
        self._timeout_s = timeout_s
        # Generation bounds fit an 8 GB CPU-only host: small context (one
        # image + prompt needs far less than 128K), capped output (our JSON
        # is a few hundred tokens), default 5m keep-alive (no concurrent
        # models; memory pressure stays at one resident model).
        self._options = {"num_ctx": num_ctx, "num_predict": num_predict}
        if num_thread > 0:
            # Owner lever: fewer threads = quieter/cooler, slower inference.
            self._options["num_thread"] = num_thread
        self._keep_alive = keep_alive
        self._caller = caller  # test seam: (image_bytes, mime, prompt_text) -> raw text

    def _chat_url(self) -> str:
        return self._host + "/api/chat"

    def _direct_call(self, image_bytes: bytes, mime: str, prompt_text: str) -> str:
        del mime  # Ollama sniffs the image bytes itself; kept for interface parity.
        body = json.dumps({
            "model": self.model_id,
            "stream": False,
            "format": "json",
            "keep_alive": self._keep_alive,
            "options": self._options,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text,
                 "images": [base64.b64encode(image_bytes).decode("ascii")]},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            self._chat_url(), data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise AIError("ollama model not found: %s" % self.model_id) from exc
            raise _classify_provider_error(exc) from exc
        except Exception as exc:  # refused/timeout/DNS: offline backend is down
            raise _classify_provider_error(exc) from exc
        try:
            return payload["message"]["content"] or ""
        except (KeyError, TypeError) as exc:
            raise AIBadResponse("unexpected ollama response shape") from exc

    def _call_with_timeout(self, image_bytes: bytes, mime: str, prompt_text: str) -> str:
        fn = self._caller or self._direct_call
        return _run_with_timeout(
            lambda: fn(image_bytes, mime, prompt_text), self._timeout_s)

    def ping(self) -> bool:
        """True iff the local server answers AND the configured model is present.

        Read-only GET, short timeout, no inference cost. Anything else → False.
        """
        try:
            with urllib.request.urlopen(self._host + "/api/tags", timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return False
        try:
            names = [m.get("name", "") for m in data.get("models", [])]
        except (AttributeError, TypeError):
            return False
        return self.model_id in names

    def analyze(self, image_bytes: bytes, mime: str, hint: str | None) -> dict:
        prompt = SYSTEM_PROMPT if not hint else SYSTEM_PROMPT + "\nObserver context: " + hint
        try:
            raw = self._call_with_timeout(image_bytes, mime, prompt)
        except AIError:
            raise
        except Exception as exc:
            raise _classify_provider_error(exc) from exc
        try:
            return _parse_analysis(raw, self.model_id)
        except AIBadResponse as first:
            repair = REPAIR_PROMPT.format(error=first.detail)
            try:
                raw2 = self._call_with_timeout(image_bytes, mime, repair)
            except AIError:
                raise
            except Exception as exc:
                raise _classify_provider_error(exc) from exc
            return _parse_analysis(raw2, self.model_id)  # raises AIBadResponse if still bad


def build_service(model_id: str, api_key: str, timeout_s: int,
                  provider: str = "gemini",
                  ollama_host: str = "http://localhost:11434",
                  ollama_model: str = "gemma4:e2b",
                  max_output_tokens: int = 1024,
                  ollama_num_ctx: int = 4096,
                  ollama_num_predict: int = 1024,
                  ollama_keep_alive: str = "5m",
                  ollama_num_thread: int = 0) -> AIService:
    """Construct exactly one backend. Unknown providers fail fast — never guess."""
    name = (provider or "gemini").strip().lower()
    if name == "gemini":
        return GeminiAdapter(model_id=model_id, api_key=api_key, timeout_s=timeout_s,
                             max_output_tokens=max_output_tokens)
    if name == "ollama":
        return OllamaAdapter(model_id=ollama_model, host=ollama_host,
                             timeout_s=timeout_s, num_ctx=ollama_num_ctx,
                             num_predict=ollama_num_predict,
                             keep_alive=ollama_keep_alive,
                             num_thread=ollama_num_thread)
    raise ValueError("unknown AI_PROVIDER %r (expected 'gemini' or 'ollama')"
                     % provider)


def utcnow() -> str:
    return _utcnow()


def current_time_s() -> float:
    return time.time()
