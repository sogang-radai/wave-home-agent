from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    account_id: str = Field(..., description="WaveHome account id managed by the C++ server.")
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    task: str
    answer: str
    intent: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


ReportKind = Literal[
    "weekly_sleep_report",
    "nightly_sleep_report",
    "weekly_posture_report",
    "daily_posture_report",
]


class ReportRequest(BaseModel):
    account_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportResponse(BaseModel):
    task: ReportKind
    title: str
    summary: str
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class ActionRecommendationRequest(BaseModel):
    account_id: str
    goal: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionRecommendationResponse(BaseModel):
    task: str
    summary: str
    recommendations: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
