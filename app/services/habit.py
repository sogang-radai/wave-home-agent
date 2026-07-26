"""Habit Builder business logic: 후보 목록을 받아 습관 후보를 생성하는 단일 LLM 호출.

app/services/sleep_analysis.py::_run_plan 과 동일한 패턴 — gather(db/query 툴 루프) 없이
백엔드가 candidates/existingHabits 를 인라인으로 넘겨주므로 invoke_structured 한 번으로
끝난다. app/services/job_common.py 의 공용 job 골격을 그대로 재사용한다.
"""

import json
import logging

from app.schemas.habit import GeneratedHabitBatch, HabitBuilderRequest
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

HABIT_KIND = "habit_builder"


def create_habit_job(body: HabitBuilderRequest) -> JobRef:
    dedupe_key = f"{HABIT_KIND}:{body.userId}:{body.date}"
    job = create_job_or_409(HABIT_KIND, dedupe_key=dedupe_key)
    spawn(_run_generation(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_generation(job_id: str, body: HabitBuilderRequest) -> None:
    job_store.mark_running(job_id)

    prompt = load_prompt(
        "habit",
        "generate",
        user_id=body.userId,
        date=body.date,
        candidates=json.dumps([c.model_dump() for c in body.candidates], ensure_ascii=False),
        existing_habits=json.dumps([h.model_dump() for h in body.existingHabits], ensure_ascii=False),
    )

    result = await invoke_structured(GeneratedHabitBatch, prompt, fallback=GeneratedHabitBatch(items=[]))
    items = [item.model_dump() for item in result.items]

    job_store.complete(job_id, {"items": items})
