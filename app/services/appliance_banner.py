"""Appliance-control banner: turns backend-computed per-room light on/off counts
into one natural-language sentence, no gather step — mirrors
app/services/dashboard_summary.py's single invoke_structured-call shape.
"""

import json
import logging

from app.schemas.appliance_banner import ApplianceBannerRequest, ApplianceRoomState, GeneratedBanner
from app.schemas.jobs import JobRef
from app.services.job_common import create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

APPLIANCE_BANNER_KIND = "appliance_banner"


def _rule_based_banner(rooms: list[ApplianceRoomState]) -> GeneratedBanner:
    """No-LLM fallback: same clause-building logic the old frontend/C++ deterministic
    version used, kept here so a failed LLM call still degrades to a correct sentence."""
    lit = [r for r in rooms if r.total > 0]
    if not lit:
        return GeneratedBanner(headline="가전 제어", body="켜진 조명이 없어요.")

    clauses = []
    for r in lit:
        if r.on == 0:
            clauses.append(f"{r.room} 조명 꺼짐")
        elif r.on == r.total:
            clauses.append(f"{r.room} 조명 {r.total}개 켜짐")
        else:
            clauses.append(f"{r.room} 조명 {r.on}/{r.total}개 켜짐")

    return GeneratedBanner(headline="가전 제어", body="현재 " + " · ".join(clauses))


def create_appliance_banner_job(body: ApplianceBannerRequest) -> JobRef:
    dedupe_key = f"{APPLIANCE_BANNER_KIND}:{json.dumps([r.model_dump() for r in body.rooms], sort_keys=True)}"
    job = create_job_or_409(APPLIANCE_BANNER_KIND, dedupe_key=dedupe_key)
    spawn(_run_generation(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_generation(job_id: str, body: ApplianceBannerRequest) -> None:
    job_store.mark_running(job_id)

    prompt = load_prompt(
        "banner",
        "appliance_control",
        rooms=json.dumps([r.model_dump() for r in body.rooms], ensure_ascii=False),
    )

    result = await invoke_structured(GeneratedBanner, prompt, fallback=_rule_based_banner(body.rooms))
    job_store.complete(job_id, result.model_dump())
