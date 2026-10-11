"""Pydantic contracts mirroring API.md section 5 + frontend src/lib/api.ts, field for field.

Backend enforces; frontend pre-validates save forms only.
"""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


ShortStr140 = Annotated[str, Field(max_length=140)]


class Experiment(StrictModel):
    title: str = Field(min_length=1, max_length=140)
    steps: list[str] = Field(min_length=2, max_length=4)
    materials: list[str] = Field(min_length=1, max_length=8)
    safety_notes: list[str] = Field(min_length=1, max_length=6)
    estimated_minutes: Literal[5, 10, 15]


class AIAnalysis(StrictModel):
    observed_features: list[ShortStr140] = Field(min_length=1, max_length=6)
    cautious_explanation: str = Field(min_length=1, max_length=800)
    uncertainty: list[str] = Field(min_length=1, max_length=4)
    experiment: Experiment
    model_id: str = Field(min_length=1, max_length=64)
    disclaimer: str = Field(min_length=1, max_length=500)


class AnalyzeResponse(StrictModel):
    temp_image_id: str
    image_preview_url: str
    analysis: AIAnalysis


class HealthResponse(StrictModel):
    status: str
    version: str
    db: str
    ai: str
    model_id: str
    uptime_s: int
    # Additive (M-auto): deployment provider mode; old clients ignore it.
    provider: str = "gemini"


class ApiErrorBody(StrictModel):
    error: dict
    request_id: str


# Journal contracts (M3 implements these routes; schemas ship with M1 so the
# frozen AIAnalysis shape is fixed before any row is written).
class JournalEntry(StrictModel):
    id: str
    title: str
    created_at: str
    image_url: str
    thumbnail_url: str
    analysis: Optional[AIAnalysis] = None
    user_notes: str = Field(min_length=1, max_length=2000)
    experiment_done: bool = False
    experiment_result: Optional[str] = Field(default=None, max_length=2000)


class JournalListItem(StrictModel):
    id: str
    title: str
    created_at: str
    thumbnail_url: str
    has_ai: bool = False
    experiment_done: bool = False


class JournalListResponse(StrictModel):
    entries: list[JournalListItem] = Field(default_factory=list)
    total: int = 0
