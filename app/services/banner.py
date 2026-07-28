"""Habit banner synthesis: merges a small set of pre-selected active habits into one
natural-language banner (headline+body), no gather step — mirrors app/services/habit.py
and app/services/sleep_analysis.py::_run_plan's single invoke_structured-call shape.
"""

import json
import logging

from app.schemas.banner import BannerHabit, GeneratedBanner, HabitBannerRequest
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

BANNER_KIND = "habit_banner"


def _fallback_banner(habits: list[BannerHabit]) -> GeneratedBanner:
    """No-synthesis fallback: just surface the single strongest habit verbatim,
    same content the pure-SQL bestActiveHabitBanner() path would already show —
    a failed LLM call should degrade to that, not to an empty/error banner."""
    if not habits:
        return GeneratedBanner(headline="", body="")
    top = max(habits, key=lambda h: h.confidence)
    return GeneratedBanner(headline=top.title, body=top.description)


def create_banner_job(body: HabitBannerRequest) -> JobRef:
    dedupe_key = f"{BANNER_KIND}:{body.userId}:{body.surface}:{body.date}"
    job = create_job_or_409(BANNER_KIND, dedupe_key=dedupe_key)
    spawn(_run_generation(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_generation(job_id: str, body: HabitBannerRequest) -> None:
    job_store.mark_running(job_id)

    prompt = load_prompt(
        "banner",
        body.surface,  # "weekly_plan" -> prompts/banner/weekly_plan.txt
        user_id=body.userId,
        date=body.date,
        habits=json.dumps([h.model_dump() for h in body.habits], ensure_ascii=False),
    )

    result = await invoke_structured(GeneratedBanner, prompt, fallback=_fallback_banner(body.habits))
    job_store.complete(job_id, result.model_dump())
