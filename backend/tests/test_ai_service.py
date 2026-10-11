"""AIService: validation, repair retry, error mapping. Provider is stubbed."""

import json

import pytest

from app.services import ai_service
from tests.conftest import VALID_ANALYSIS, make_image


def good_adapter(**kw):
    kw.setdefault("model_id", "gemma-4-26b-a4b-it")
    kw.setdefault("api_key", "placeholder-not-a-real-key")
    kw.setdefault("timeout_s", 30)
    return ai_service.GeminiAdapter(**kw)


def test_success_returns_validated_dict_with_model_and_timestamp():
    out = good_adapter(caller=lambda b, m, p: json.dumps(VALID_ANALYSIS)).analyze(
        b"img", "image/jpeg", None)
    assert out["model_id"] == "gemma-4-26b-a4b-it" and out["analyzed_at"]


def test_repair_retry_then_success():
    calls = []

    def flaky(_b, _m, _p):
        calls.append(1)
        return "not json {" if len(calls) == 1 else json.dumps(VALID_ANALYSIS)

    good_adapter(caller=flaky).analyze(b"img", "image/jpeg", None)
    assert len(calls) == 2


def test_double_failure_raises_bad_response():
    adapter = good_adapter(caller=lambda _b, _m, _p: "nope")
    with pytest.raises(ai_service.AIBadResponse) as e:
        adapter.analyze(b"img", "image/jpeg", None)
    assert (e.value.code, e.value.status) == ("ai_bad_response", 502)


def test_provider_error_mapping():
    cases = [("unauthenticated 401", ai_service.AIAuthError, "api_auth_error", 503),
             ("429 RESOURCE_EXHAUSTED quota", ai_service.AIQuotaError, "api_quota_exhausted", 503),
             ("connection reset", ai_service.AIError, "ai_unavailable", 503)]

    def boom(_b, _m, _p, msg=""):
        raise RuntimeError(msg)

    for msg, cls, code, status in cases:
        with pytest.raises(cls) as e:
            good_adapter(caller=lambda b, m, p, _msg=msg: boom(b, m, p, _msg)).analyze(
                b"img", "image/jpeg", None)
        assert (e.value.code, e.value.status) == (code, status)


def test_timeout_and_missing_credentials():
    def slow(_b, _m, _p):
        import time
        time.sleep(2)

    with pytest.raises(ai_service.AITimeout):
        good_adapter(timeout_s=0, caller=slow).analyze(b"img", "image/jpeg", None)
    with pytest.raises(ai_service.AIError):
        ai_service.GeminiAdapter(model_id="m", api_key="").analyze(b"img", "image/jpeg", None)


def test_ping_is_config_only_and_adapter_has_no_key_leak():
    assert good_adapter().ping() is True
    assert ai_service.GeminiAdapter(model_id="m", api_key="").ping() is False
    assert "placeholder" not in repr(good_adapter(caller=lambda b, m, p: "{}"))
