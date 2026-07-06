from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ReportDomain = Literal["sleep", "posture"]
ReportPeriod = Literal["daily", "weekly"]


class ReportTurnRequest(BaseModel):
    userId: int
    periodStart: str
    metrics: dict[str, Any]
    raw: Optional[dict[str, Any]] = None


class ReportTurnResponse(BaseModel):
    domain: ReportDomain
    period: ReportPeriod
    periodStart: str
    summary: str
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
