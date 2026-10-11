"""Output-style contract: shared beginner instructions, frozen schema.

Provider I/O is stubbed/mocked. No network, no keys. These tests pin the
prompt wording both adapters send and the schema bounds — they do not judge
model prose quality (that needs the manual same-photo check in both modes).
"""

import json

import pytest

from app import schemas
from app.services import ai_service
from tests.conftest import VALID_ANALYSIS, make_image


def test_both_providers_send_shared_style_instructions(monkeypatch):
    seen_gemini = {}

    def gemini_caller(_b, _m, prompt_text):
        seen_gemini["prompt"] = prompt_text
        return json.dumps(VALID_ANALYSIS)

    ai_service.GeminiAdapter(model_id="m", api_key="k",
                             caller=gemini_caller).analyze(b"img", "image/jpeg", None)
    assert ai_service.SYSTEM_PROMPT in seen_gemini["prompt"]

    seen_ollama = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"message": {"content": json.dumps(VALID_ANALYSIS)}}).encode()

    def capture(req):
        seen_ollama.update(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", capture)
    ai_service.OllamaAdapter(model_id="m", host="http://h:1").analyze(
        b"img", "image/jpeg", None)
    assert seen_ollama["messages"][0] == {"role": "system",
                                          "content": ai_service.SYSTEM_PROMPT}


def test_style_rules_present_in_shared_prompt():
    prompt = ai_service.SYSTEM_PROMPT
    for required in ("short sentences", "plain everyday English",
                     "step-by-step thinking process", "Never repeat the same point",
                     "3 to 5 short visible traits", "hedged words",
                     "Never invent species names, measurements, locations, weather",
                     "Never claim the user performed any experiment",
                     "Never encourage tasting, ingesting, damaging, or handling",
                     "school student", "cannot tell",
                     "2 or 3 short sentences describing the visible subject",
                     "never repeat generic limitations",
                     "observing the subject in place",
                     "Do not ask users to pick, collect, or handle",
                     "adds meaning to the bullets",
                     "never state the obvious",
                     "observing in place from a distance",
                     "stated once, not repeated",
                     "Never infer plant hardiness, typical habitat, health, growing conditions",
                     "clearly labeled uncertain and genuinely useful",
                     "If nothing beyond the bullets is supported, keep it to one very short sentence"):
        assert required in prompt, required


def test_schema_bounds_frozen():
    # Prompt guides 3-5 features / 1-3 uncertainty / 3-4 steps; the schema
    # stays permissive so older valid outputs still validate.
    assert schemas.AIAnalysis.model_validate(VALID_ANALYSIS)
    assert schemas.AIAnalysis.model_validate(
        dict(VALID_ANALYSIS, observed_features=["a"] * 6))
    with pytest.raises(Exception):
        schemas.AIAnalysis.model_validate(
            dict(VALID_ANALYSIS, observed_features=["a"] * 7))


def test_uncertainty_safety_experiment_required():
    for key, bad in (("uncertainty", []),
                     ("experiment", dict(VALID_ANALYSIS["experiment"], safety_notes=[])),
                     ("experiment", dict(VALID_ANALYSIS["experiment"], steps=["only one"]))):
        with pytest.raises(Exception):
            schemas.AIAnalysis.model_validate(dict(VALID_ANALYSIS, **{key: bad}))
