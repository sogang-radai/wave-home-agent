"""weekly-plan-analysis-api.md 비즈니스 로직: 주간 계획 배너 생성을 job 으로 처리한다."""

import logging
from datetime import date

from app.errors import AgentApiError
from app.graph.weekly_plan_graph import build as build_weekly_plan_graph
from app.schemas.jobs import JobRef
from app.schemas.weekly_plan import WeeklyPlanReportRequest, WeeklyPlanReportResult
from app.services.embeddings import generate_embedding
from app.services.job_common import apply_embedding, create_job_or_409, spawn
from app.services.jobs import job_store


logger = logging.getLogger(__name__)

REPORT_KIND = "weekly_plan_report"

_graph = build_weekly_plan_graph()


def create_report_job(body: WeeklyPlanReportRequest) -> JobRef:
    if date.fromisoformat(body.periodStart).weekday() != 0:
        raise AgentApiError(
            400, "INVALID_WEEK_START", "periodStart는 해당 주의 월요일 날짜여야 합니다.", field="periodStart"
        )

    dedupe_key = f"{REPORT_KIND}:{body.userId}:{body.periodStart}"
    job = create_job_or_409(REPORT_KIND, dedupe_key=dedupe_key)
    spawn(_run_report(job.job_id, body))
    return JobRef(jobId=job.job_id)


async def _run_report(job_id: str, body: WeeklyPlanReportRequest) -> None:
    job_store.mark_running(job_id)
    result = await _graph.ainvoke({"user_id": body.userId, "period_start": body.periodStart, "rounds": 0})

    embedding, _embedding_model, failed = await apply_embedding(
        job_id, result["report_text"], None, body.embed, generate_embedding=generate_embedding
    )
    if failed:
        return

    response = WeeklyPlanReportResult(
        periodStart=body.periodStart,
        headline=result.get("headline"),
        reportText=result["report_text"],
        embedding=embedding,
    )
    job_store.complete(job_id, response.model_dump())
