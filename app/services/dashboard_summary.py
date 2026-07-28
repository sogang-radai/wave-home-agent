"""Dashboard weekly summary: turns backend-computed sleep/power/appliance-control
stats into a natural-language banner (headline + a few sentences of body), no
gather step — mirrors app/services/banner.py's single invoke_structured-call
shape (metrics-in, wording-out instead of habits-in).
"""

import json
import logging
from typing import Any

from app.schemas.dashboard_summary import DashboardWeeklySummaryRequest, GeneratedDashboardSummary
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

DASHBOARD_SUMMARY_KIND = "dashboard_summary"


def _rule_based_summary(metrics: dict[str, Any]) -> GeneratedDashboardSummary:
    """No-LLM fallback: a short deterministic sentence built directly from the
    metrics."""
    parts: list[str] = []
    sleep = metrics.get("sleep")
    if isinstance(sleep, dict) and sleep.get("avgBedtime"):
        parts.append(f"평균 {sleep['avgBedtime']}에 취침")
    power = metrics.get("power")
    if isinstance(power, dict) and power.get("totalKwh") is not None:
        parts.append(f"전력 {power['totalKwh']}kWh 사용")
    appliance = metrics.get("appliance")
    if isinstance(appliance, dict) and appliance.get("executionCount") is not None:
        parts.append(f"가전 {appliance['executionCount']}회 제어")

    body = "이번 주 " + ", ".join(parts) + "했어요." if parts else "이번 주 데이터가 아직 부족해요."
    return GeneratedDashboardSummary(headline="이번 주 요약", body=body)


def create_dashboard_summary_job(body: DashboardWeeklySummaryRequest) -> JobRef:
    dedupe_key = f"{DASHBOARD_SUMMARY_KIND}:{body.userId}:{body.date}"
    job = create_job_or_409(DASHBOARD_SUMMARY_KIND, dedupe_key=dedupe_key)
    spawn(_run_generation(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_generation(job_id: str, body: DashboardWeeklySummaryRequest) -> None:
    job_store.mark_running(job_id)

    prompt = load_prompt(
        "dashboard",
        "weekly_summary",
        user_id=body.userId,
        date=body.date,
        metrics=json.dumps(body.metrics, ensure_ascii=False),
    )

    result = await invoke_structured(
        GeneratedDashboardSummary, prompt, fallback=_rule_based_summary(body.metrics)
    )

    job_store.complete(job_id, result.model_dump())
