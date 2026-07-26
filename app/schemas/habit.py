"""POST /insight/v1/habits 요청/응답 스키마.

Habit Builder는 insight_graph.py 와 달리 gather 단계(db/query 툴 루프)를 쓰지 않는다 —
후보(candidates)와 기존 활성 습관(existingHabits)을 백엔드가 이미 계산해서 인라인으로
넘겨주므로, sleep/power report 생성과 동일하게 단일 invoke_structured 호출로 끝난다
(app/services/sleep_analysis.py::_run_plan 패턴 참고). confidence 는 이 스키마에 없다 —
LLM이 숫자를 만들지 않고, 백엔드가 candidate 의 실측 days/window 로부터 직접 계산한다.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


HabitType = Literal["sleep", "power", "gesture", "lifestyle"]


class HabitCandidate(BaseModel):
    event: str
    label: str = ""
    deviceName: str = ""
    days: int
    window: int


class ExistingHabit(BaseModel):
    id: int
    title: str
    event: str = ""


class HabitBuilderRequest(BaseModel):
    userId: int
    date: str
    candidates: list[HabitCandidate] = Field(default_factory=list)
    existingHabits: list[ExistingHabit] = Field(default_factory=list)


class GeneratedHabit(BaseModel):
    event: str
    habitType: HabitType
    title: str
    description: str
    existingHabitId: Optional[int] = None


class GeneratedHabitBatch(BaseModel):
    """invoke_structured() 의 top-level 스키마 — list 는 바로 구조화 출력 스키마로 못 써서
    한 겹 감싼다 (app/schemas/insight.py::GeneratedInsightBatch 와 동일한 이유)."""

    items: list[GeneratedHabit] = Field(default_factory=list)
