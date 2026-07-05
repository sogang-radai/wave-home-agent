from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "unknown"]
Domain = Literal["sleep", "posture", "observation", "lifestyle"]


class Insight(BaseModel):
    domain: Domain
    summary: str
    risk_level: RiskLevel
    positive_points: list[str] = Field(default_factory=list)
    negative_points: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence: float


class HealthSummary(BaseModel):
    summary: str
    risk_level: RiskLevel
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    domains: list[Insight] = Field(default_factory=list)
    confidence: float
