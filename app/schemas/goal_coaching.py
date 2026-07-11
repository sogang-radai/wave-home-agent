"""goal-coaching 기능(신규)의 `/goal-coaching/v1/reports` 요청/응답 스키마.

`goal`/`goal_coaching_report`/`goal_recommendation` 은 이 에이전트가 직접 읽지 않는 OUTPUT
전용 테이블이다 — C++ 백엔드가 `goal_coaching_report`(과거 요약/전망)와 `goal_recommendation`
(insight 와 동격의 별도 테이블)에 이 그래프의 결과를 그대로 써넣는다. 그래서
GoalCoachingResult 에는 sleep/power 리포트처럼 goal_coaching_report 행에 대응하는 필드
(pastSummary/projection/projectedMetrics)와 goal_recommendation 행 목록(items)이 함께
들어있다 — C++ 쪽이 한 번의 job 결과에서 두 테이블에 나눠 쓸 수 있게 하기 위함이다.

ruleJson/scheduleTaskJson 을 app/schemas/insight.py 처럼 CreateRuleRequest/
CreateScheduleTaskRequest 로 강타입하지 않고 plain dict 로 둔 이유: goal_recommendation 은
insight 와 달리 사용자가 "승인"하기 전까지 실제 rule/schedule_task 로 변환되지 않는(그 변환은
C++ 백엔드가 승인 시점에 수행) 순수 제안 데이터이므로, 여기서 강타입 검증까지 걸 필요가 없다.
대신 app/graph/insight_graph.py 의 _validate_automation_rules() 를 그대로 재사용해
device/action 존재 여부는 사후 검증한다(app/graph/goal_coaching_graph.py 참고).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


GoalCategory = Literal["sleep", "posture", "mental", "life", "diet"]


class GoalCoachingRequest(BaseModel):
    userId: int
    goalId: int
    goalTitle: str
    category: GoalCategory
    periodStart: str  # 'YYYY-MM-DD', 리포트 생성 기준일. 분석 구간은 periodStart-30일..periodStart.
    embed: bool = False


class GoalRecommendationItem(BaseModel):
    kind: Literal["action", "goal", "tip"]
    title: str
    text: str
    actionable: bool = False
    actionType: Optional[Literal["schedule_task", "automation_rule"]] = None
    ruleJson: Optional[dict] = None
    scheduleTaskJson: Optional[dict] = None

    @model_validator(mode="after")
    def _backfill_action_type(self) -> "GoalRecommendationItem":
        """app/schemas/insight.py의 GeneratedInsight._backfill_action_type과 같은 이유로
        필요하지만, 한 단계 더 나간다: 그쪽은 actionType이 비어도 scheduleTaskJson/ruleJson이
        채워져 있으면 역으로 채워주기만 하고, actionable=true인데 actionType도 두 json도 다
        비어 있는 경우는 그대로 통과시킨다(goal_recommendation 테이블에 처음 이 CHECK
        (actionable=0 OR action_type IS NOT NULL)를 걸어보니 실측으로 이 경우가 실제로
        나왔다 — LLM이 "이건 실행 가능한 항목"이라고 표시만 하고 실행 데이터를 안 채운
        경우). 그래서 여기서는 백필 후에도 actionType이 없으면 actionable을 강제로
        false로 내려서, 지어낼 수 없는 걸 지어내는 대신 "실행 불가 항목"으로 정직하게
        되돌린다."""
        if self.actionType is None:
            if self.scheduleTaskJson is not None:
                self.actionType = "schedule_task"
            elif self.ruleJson is not None:
                self.actionType = "automation_rule"
        self.actionable = self.actionType is not None
        return self


class GoalCoachingContent(BaseModel):
    """invoke_structured() 의 top-level 스키마."""

    pastSummary: str
    projection: str
    projectedMetrics: dict  # 예: {"completionRate": 0.62, "trend": "improving"|"steady"|"declining", "streakDays": 4}
    items: list[GoalRecommendationItem] = Field(default_factory=list)


class GoalCoachingResult(BaseModel):
    periodStart: str
    pastSummary: str
    projection: str
    projectedMetrics: dict
    items: list[GoalRecommendationItem]
    # NOTE: sleep/power 리포트와 달리 top-level "reportText" 플랫 문자열 필드가 없다 — 이
    # 기능의 C++ 호출부는 runSleepJobSync 를 재사용하지 않고 이 기능 전용 폴러
    # (runGoalCoachingJobSync 가정)를 새로 만드는 중이라, 이 더 풍부한 JSON 형태를 그대로 읽을
    # 수 있다. app/services/job_common.py 의 job_response() 가 job.result 를 가공 없이 그대로
    # 내려주는 것으로 확인했다(JSONResponse(content={..., "result": job.result})) — 따라서
    # job_store.complete(job_id, GoalCoachingResult(...).model_dump()) 로 넘긴 dict 모양이
    # GET .../jobs/{id} 응답의 result 필드에 그대로 나타난다.
