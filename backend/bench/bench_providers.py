"""Repeatable latency benchmark for both providers (same image, same prompt).

NOT executed automatically — the owner runs it with live backends:
  # offline (free, local only):
  py -3.11 bench/bench_providers.py --provider ollama --image C:\\path\\leaf.jpg --runs 5
  # online (uses YOUR key and billing/quota; free-tier data terms apply):
  $env:GEMINI_API_KEY = "<your key>"
  py -3.11 bench/bench_providers.py --provider gemini --image C:\\path\\leaf.jpg --runs 5

Run from backend/ so `app` imports. Records per run (JSONL on stdout;
redirect to a file YOU keep out of git), then a summary. Run 1 is labeled
cold, runs 2+ warm (true cold-start needs a model unload between runs —
see report; treat run 1 as orientation, not a cold-start guarantee).
Never prints keys, image bytes, prompts, or model text — timings only.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.services import ai_service, images  # noqa: E402


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    low, high = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    frac = k - low
    return sorted_vals[low] * (1 - frac) + sorted_vals[high] * frac


def summarize(records):
    """Pure stats over run records. Unit-tested with synthetic timings."""
    ok = [r for r in records if r.get("ok")]
    cold = [r for r in ok if r.get("cold")]
    warm = [r for r in ok if not r.get("cold")]
    by_phase = {}
    for phase in ("pre_ms", "provider_ms", "total_ms"):
        vals = sorted(r[phase] for r in warm)
        by_phase[phase] = {
            "n": len(vals),
            "mean": sum(vals) / len(vals) if vals else None,
            "p50": percentile(vals, 50),
            "p95": percentile(vals, 95),
        }
    return {
        "runs": len(records),
        "ok": len(ok),
        "failed": len(records) - len(ok),
        "cold_total_ms": cold[0]["total_ms"] if cold else None,
        "warm": {p: {k: v for k, v in by_phase[p].items() if k != "n"} for p in by_phase},
        "warm_n": len(warm),
    }


def build_adapter(settings, provider):
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise SystemExit("GEMINI_API_KEY is not set in the environment")
        return ai_service.GeminiAdapter(
            model_id=settings.ai_model_id, api_key=settings.gemini_api_key,
            timeout_s=settings.ai_timeout_s,
            max_output_tokens=settings.gemini_max_output_tokens)
    return ai_service.OllamaAdapter(
        model_id=settings.ollama_model, host=settings.ollama_host,
        timeout_s=settings.ai_timeout_s, num_ctx=settings.ollama_num_ctx,
        num_predict=settings.ollama_num_predict,
        keep_alive=settings.ollama_keep_alive)


def main(argv=None):
    args_parser = argparse.ArgumentParser(description="Verdantra latency benchmark")
    args_parser.add_argument("--provider", choices=["gemini", "ollama"], required=True)
    args_parser.add_argument("--image", required=True)
    args_parser.add_argument("--runs", type=int, default=5)
    args = args_parser.parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")

    settings = Settings()
    with open(args.image, "rb") as fh:
        raw = fh.read()
    mime = images.sniff_mime(raw[:12])
    if mime is None or len(raw) > settings.max_image_bytes:
        raise SystemExit("test image rejected by the documented intake rules")
    images.validate_bytes(raw, settings.max_image_bytes)

    adapter = build_adapter(settings, args.provider)
    records = []
    for i in range(args.runs):
        t0 = time.perf_counter()
        t_pre = t_ai = 0
        ok, code = True, "ok"
        try:
            t1 = time.perf_counter()
            tx_bytes, tx_mime = images.prepare_transmit(
                images.sanitize(raw, mime)[0], mime,
                settings.transmit_max_edge, settings.transmit_jpeg_quality)
            t_pre = int((time.perf_counter() - t1) * 1000)
            t2 = time.perf_counter()
            adapter.analyze(tx_bytes, tx_mime, None)
            t_ai = int((time.perf_counter() - t2) * 1000)
        except ai_service.AIError as exc:
            ok, code = False, exc.code
        except Exception as exc:  # never let harness internals leak raw errors
            ok, code = False, type(exc).__name__
        total = int((time.perf_counter() - t0) * 1000)
        records.append({"provider": args.provider, "model": adapter.model_id,
                        "run": i + 1, "cold": i == 0, "ok": ok, "code": code,
                        "image_bytes": len(raw), "pre_ms": t_pre,
                        "provider_ms": t_ai, "total_ms": total})
        print(json.dumps(records[-1]), flush=True)
    print(json.dumps({"summary": summarize(records)}), flush=True)
    return 0 if all(r["ok"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
