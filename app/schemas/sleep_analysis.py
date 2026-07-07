"""docs/api.md §1.4 Sleep Analysis API request/response types (teammate.md's
SleepStatRow/SleepSessionRow/SummaryRequest/SummaryResponse/ReportRequest/ReportResponse,
prefixed with Sleep in code to disambiguate from app/schemas/report_turn.py's unrelated
ReportTurnRequest/Response used by POST /reports/v1/{domain}/{period})."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SleepStatRow(BaseModel):
    id: int
    userId: int
    roomId: int
    sessionId: Optional[int] = None
    granularity: Literal["1m", "30m"]
    timeStart: str
    timeEnd: Optional[str] = None
    coverage: float
    stageLabel: Optional[str] = None
    stageRatio: Optional[dict[str, float]] = None
    stageConfidence: Optional[float] = None
    statusRatio: Optional[dict[str, float]] = None
    tossMean: Optional[float] = None
    tossMax: Optional[float] = None
    tossP90: Optional[float] = None
    tossEvents: Optional[int] = None
    tossRatio: Optional[dict[str, float]] = None
    hrMean: Optional[float] = None
    hrMin: Optional[float] = None
    hrMax: Optional[float] = None
    hrStd: Optional[float] = None
    brMean: Optional[float] = None
    brMin: Optional[float] = None
    brMax: Optional[float] = None
    brStd: Optional[float] = None
    snoreRatio: Optional[float] = None
    envTemp: Optional[float] = None
    envLux: Optional[float] = None
    envNoise: Optional[float] = None


class SleepSessionRow(BaseModel):
    id: int
    userId: int
    roomId: int
    radarId: int
    stationId: Optional[int] = None
    nightDate: str
    onset: Optional[str] = None
    finalWake: Optional[str] = None
    timeInBedS: Optional[int] = None
    asleepTotalS: Optional[int] = None
    efficiency: Optional[float] = None
    stageTotals: Optional[dict[str, Any]] = None
    tossEvents: Optional[int] = None
    hrMean: Optional[float] = None
    brMean: Optional[float] = None
    snoreRatio: Optional[float] = None


class SleepSummaryRequest(BaseModel):
    window: SleepStatRow
    minutes: Optional[list[SleepStatRow]] = None
    embed: bool = True
    model: Optional[str] = None
    embeddingModel: Optional[str] = None


class SleepSummaryResponse(BaseModel):
    statId: int
    summaryText: str
    embedding: Optional[list[float]] = None
    model: str
    embeddingModel: Optional[str] = None


class SleepReportRequest(BaseModel):
    userId: int
    period: Literal["daily", "weekly"]
    periodStart: str
    metrics: dict[str, Any]
    sessions: list[SleepSessionRow] = Field(default_factory=list)
    stats30m: list[SleepStatRow] = Field(default_factory=list)
    embed: bool = True
    model: Optional[str] = None
    embeddingModel: Optional[str] = None


class SleepReportResponse(BaseModel):
    period: Literal["daily", "weekly"]
    periodStart: str
    reportText: str
    embedding: Optional[list[float]] = None
    model: str
    embeddingModel: Optional[str] = None
