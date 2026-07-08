"""insight-generation-api.md 의 `/insight/v1/insights` 요청/응답 스키마.

`ruleJson`/`scheduleTaskJson` 은 문서에서 `object | null` 로만 정의돼 있지만, 이미
`app/tools/rules_internal.py`(automation_rule 쓰기)·`app/tools/schedule_tasks_internal.py`
(schedule_task 쓰기)에 해당 타입이 있으므로 `object` 대신 그대로 참조한다 — 문서 간
드리프트를 막고, 백엔드에 실제로 쓸 수 있는 형태인지 pydantic 검증까지 거치게 한다.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.tools.rules_internal import CreateRuleRequest
from app.tools.schedule_tasks_internal import CreateScheduleTaskRequest


InsightSurface = Literal["dashboard_banner", "weekly_plan", "sleep_report", "posture_report", "power"]
InsightKind = Literal["banner", "action", "goal", "tip"]
InsightActionType = Literal["schedule_task", "automation_rule", "reservation"]


class InsightGenerationRequest(BaseModel):
    userId: int
    surface: InsightSurface
    date: str
    context: dict[str, Any] = Field(default_factory=dict)
    embed: bool = True


class GeneratedInsight(BaseModel):
    surface: str
    kind: InsightKind
    date: str
    label: Optional[str] = None
    title: str
    text: str
    actionable: bool = False
    actionType: Optional[InsightActionType] = None
    ruleJson: Optional[CreateRuleRequest] = None
    scheduleTaskJson: Optional[CreateScheduleTaskRequest] = None
    embedding: Optional[list[float]] = None


class GeneratedInsightBatch(BaseModel):
    """invoke_structured() 의 top-level 스키마 — list 는 바로 구조화 출력 스키마로 못 써서
    한 겹 감싼다."""

    items: list[GeneratedInsight] = Field(default_factory=list)
