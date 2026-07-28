"""POST /insight/v1/habit-banner 요청/응답 스키마.

app/schemas/habit.py 와 같은 이유로 gather 단계가 없다 — 백엔드가 이미 골라낸 활성 습관
목록(habits)을 인라인으로 넘겨주고, LLM은 그걸 자연스러운 한 배너(headline+body)로
합치는 문장 작업만 한다. 대시보드 배너는 더 이상 habit 기반이 아니므로(POST
/insight/v1/dashboard-summary, app/schemas/dashboard_summary.py 참고) 이 엔드포인트는
weekly_plan(루틴 플래너) 서피스 전용이다.
"""

from typing import Literal

from pydantic import BaseModel, Field


BannerSurface = Literal["weekly_plan"]


class BannerHabit(BaseModel):
    habitType: str
    title: str
    description: str
    confidence: float


class HabitBannerRequest(BaseModel):
    userId: int
    date: str
    surface: BannerSurface
    habits: list[BannerHabit] = Field(default_factory=list)


class GeneratedBanner(BaseModel):
    headline: str
    body: str
