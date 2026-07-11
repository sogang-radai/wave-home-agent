"""goal-coaching 기능(신규) 비즈니스 로직: 목표 코칭 리포트 생성을 job 으로 처리한다.

app/services/job_common.py 의 공용 job 골격(create_job_or_409/spawn)을 insight/weekly_plan 과
동일하게 재사용한다. embed 는 항상 False 로 취급한다 - insight/weekly_plan 이전까지도
"실제 vec 저장소가 아직 없다"는 이유로 sleep/power 에만 임베딩을 붙였던 것과 같은 원칙이며,
이 요청 스키마(app/schemas/goal_coaching.py)의 embed 필드도 항상 false 로 호출된다는 전제라
apply_embedding 호출 자체를 넣지 않는다.
"""

import logging

from app.graph.goal_coaching_graph import build as build_goal_coaching_graph
from app.schemas.goal_coaching import GoalCoachingRequest, GoalCoachingResult
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store


logger = logging.getLogger(__name__)

GOAL_COACHING_KIND = "goal_coaching_report"

_graph = build_goal_coaching_graph()


def create_report_job(body: GoalCoachingRequest) -> JobRef:
    dedupe_key = f"{GOAL_COACHING_KIND}:{body.goalId}:{body.periodStart}"
    job = create_job_or_409(GOAL_COACHING_KIND, dedupe_key=dedupe_key)
    spawn(_run_report(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_report(job_id: str, body: GoalCoachingRequest) -> None:
    job_store.mark_running(job_id)
    result = await _graph.ainvoke(
        {
            "user_id": body.userId,
            "goal_id": body.goalId,
            "goal_title": body.goalTitle,
            "category": body.category,
            "period_start": body.periodStart,
            "rounds": 0,
        }
    )
    content = result["content"]
    response = GoalCoachingResult(
        periodStart=body.periodStart,
        pastSummary=content.pastSummary,
        projection=content.projection,
        projectedMetrics=content.projectedMetrics,
        items=content.items,
    )
    job_store.complete(job_id, response.model_dump())
