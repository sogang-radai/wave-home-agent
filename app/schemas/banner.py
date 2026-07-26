"""POST /insight/v1/habit-banner 요청/응답 스키마.

app/schemas/habit.py 와 같은 이유로 gather 단계가 없다 — 백엔드가 이미 골라낸 활성 습관
목록(habits)을 인라인으로 넘겨주고, LLM은 그걸 자연스러운 한 배너(headline+body)로
합치는 문장 작업만 한다. 어떤 습관을 넣을지(sleep/power/lifestyle 전부 vs lifestyle만)는
호출부(banner_generator.cpp)가 surface 별로 이미 필터링해서 보낸다 — 이 스키마/그래프는
그 경계를 모르고 그냥 받은 걸 합칠 뿐이다.
"""

from typing import Literal

from pydantic import BaseModel, Field


BannerSurface = Literal["dashboard", "weekly_plan"]


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
