"""Contract schemas mirror API.md section 5 field for field."""

import pytest
from pydantic import ValidationError

from app import schemas
from tests.conftest import VALID_ANALYSIS


def test_valid_analysis_passes():
    assert schemas.AIAnalysis.model_validate(VALID_ANALYSIS).model_id == "gemma-4-26b-a4b-it"


def test_missing_uncertainty_rejected():
    bad = dict(VALID_ANALYSIS, uncertainty=[])
    with pytest.raises(ValidationError):
        schemas.AIAnalysis.model_validate(bad)


def test_bad_minutes_and_long_lists_rejected():
    bad = dict(VALID_ANALYSIS)
    bad["experiment"] = dict(bad["experiment"], estimated_minutes=7)
    with pytest.raises(ValidationError):
        schemas.AIAnalysis.model_validate(bad)
    bad2 = dict(VALID_ANALYSIS, observed_features=["x"] * 7)
    with pytest.raises(ValidationError):
        schemas.AIAnalysis.model_validate(bad2)


def test_extra_fields_ignored_per_contract():
    ok = dict(VALID_ANALYSIS, extra_future_field="dropped")
    assert schemas.AIAnalysis.model_validate(ok).model_dump().get("extra_future_field") is None
