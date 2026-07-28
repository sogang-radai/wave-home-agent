"""POST /insight/v1/dashboard-summary 요청/응답 스키마.

대시보드 배너는 더 이상 habit 기반이 아니다 — 백엔드(banner_generator.cpp)가 최근 7일간의
수면/전력/가전 제어 실측 통계를 계산해서 인라인으로 넘겨주고, LLM은 그걸 145자 이내의 한
문장으로 요약하는 문장 작업만 한다(gather 단계 없음, app/schemas/habit.py 와 동일한 이유).
"""

from typing import Any

from pydantic import BaseModel, Field


class DashboardWeeklySummaryRequest(BaseModel):
    userId: int
    date: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class GeneratedDashboardSummary(BaseModel):
    headline: str
    body: str
