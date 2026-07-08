"""weekly-plan-analysis-api.md 의 `/weekly-plan/v1/reports` 요청/응답 스키마."""

from typing import Optional

from pydantic import BaseModel


class WeeklyPlanReportRequest(BaseModel):
    userId: int
    periodStart: str  # 해당 주 월요일 'YYYY-MM-DD'
    embed: bool = True


class WeeklyPlanReportResult(BaseModel):
    periodStart: str
    headline: Optional[str] = None
    reportText: str
    embedding: Optional[list[float]] = None
