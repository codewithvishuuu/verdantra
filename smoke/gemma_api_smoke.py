"""Verdantra M0-A hosted smoke test (time-boxed, single request).

Sends one real outdoor photo to gemma-4-26b-a4b-it via the Gemini API
and prints the model ID, elapsed time, and returned text.

Secrets: GEMINI_API_KEY is read from the process environment only.
It is never printed, logged, or written anywhere by this script.

Usage (PowerShell):
    $env:GEMINI_API_KEY = "<your key>"   # set by YOU, never committed
    py -3.11 smoke/gemma_api_smoke.py C:\\path\\to\\leaf.jpg
  or:
    $env:VERDANTRA_TEST_IMAGE = "C:\\path\\to\\leaf.jpg"
    py -3.11 smoke/gemma_api_smoke.py

Exit codes: 0 pass, 2 usage/config, 3 image problem, 4 API error.
Makes exactly one generate_content call. No retries, no persistence.
"""

import os
import sys
import time

MODEL_ID = "gemma-4-26b-a4b-it"
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Magic-byte sniff (extension alone is never trusted).
MAGIC = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}

PROMPT = (
    "You are Verdantra Field Helper. Describe only what is visibly present "
    "in this outdoor photo in 3 short bullets. Use hedged language "
    "('appears', 'may be'). Do not identify a species, give measurements, "
    "or give foraging, medical, or safety advice."
)


def fail(code, message):
    print("SMOKE-FAIL " + message[:300])
    return code


def load_image(path):
    if not path:
        return None, "no test image: pass a path argument or set VERDANTRA_TEST_IMAGE"
    if not os.path.isfile(path):
        return None, "not a file: " + path
    size = os.path.getsize(path)
    if size == 0:
        return None, "empty file: " + path
    if size > MAX_IMAGE_BYTES:
        return None, "over 10 MB limit (%d bytes): %s" % (size, path)
    with open(path, "rb") as fh:
        head = fh.read(12)
    mime = None
    for sig, (mt, _ext) in MAGIC.items():
        if head.startswith(sig):
            mime = mt
            break
    if mime is None and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        mime = "image/webp"
    if mime is None:
        return None, "unsupported format (need JPEG/PNG/WebP): " + path
    with open(path, "rb") as fh:
        return (fh.read(), mime, size), None


def scrub(text, secret):
    # Defensive: never let the key appear in output even if an SDK error echoes it.
    if secret and secret in text:
        return text.replace(secret, "[REDACTED]")
    return text


def main(argv):
    image_path = argv[1] if len(argv) > 1 else os.environ.get("VERDANTRA_TEST_IMAGE", "")
    api_key = os.environ.get("GEMINI_API_KEY", "")

    if not api_key:
        return fail(2, "config: GEMINI_API_KEY is not set in the environment")
    loaded, err = load_image(image_path)
    if err is not None:
        return fail(3, "image: " + err)
    image_bytes, mime, size = loaded

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return fail(2, "config: google-genai SDK is not importable in this interpreter")

    try:
        client = genai.Client(api_key=api_key)
        start = time.perf_counter()
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                PROMPT,
            ],
        )
        elapsed = time.perf_counter() - start
    except Exception as exc:  # noqa: BLE001 - map everything to a safe one-line report
        name = type(exc).__name__
        msg = scrub(str(exc), api_key)
        lowered = (name + " " + msg).lower()
        if "401" in lowered or "unauthenticated" in lowered or "api key" in lowered:
            return fail(4, "auth: " + name + " " + msg)
        if "429" in lowered or "resource_exhausted" in lowered or "quota" in lowered:
            return fail(4, "quota: " + name + " " + msg)
        if "404" in lowered or "not_found" in lowered or "not found" in lowered:
            return fail(4, "model: " + name + " " + msg)
        return fail(4, "api: " + name + " " + msg)

    text = scrub(response.text or "", api_key)
    print("SMOKE-PASS model=%s latency_s=%.1f image_bytes=%d" % (MODEL_ID, elapsed, size))
    print(text[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
