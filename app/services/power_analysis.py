"""docs/api.md §1.4 Power Analysis API business logic. Mirrors app/services/sleep_analysis.py."""

import json
import logging
from typing import Any

from app.errors import AgentApiError
from app.schemas.jobs import JobRef
from app.schemas.power_analysis import PowerReportRequest, PowerReportResponse
from app.services.embeddings import generate_embedding
from app.services.job_common import apply_embedding, create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_text
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

REPORT_KIND = "power_report"


def _rule_based_report(metrics: dict[str, Any]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in metrics.items()) or "제공된 지표가 없습니다."


def create_report_job(body: PowerReportRequest) -> JobRef:
    if body.target.granularity != body.period:
        raise AgentApiError(
            400,
            "INVALID_REQUEST",
            "target.granularity 는 리포트 대상(1h/24h/1w/1mo)이어야 합니다.",
            field="target.granularity",
        )

    job = create_job_or_409(REPORT_KIND, dedupe_key=f"{REPORT_KIND}:{body.target.id}")
    spawn(_run_report(job.job_id, body), job_id=job.job_id)
    return JobRef(jobId=job.job_id)


async def _run_report(job_id: str, body: PowerReportRequest) -> None:
    job_store.mark_running(job_id)
    prompt = load_prompt(
        "power",
        "report",
        period=body.period,
        period_start=body.periodStart,
        metrics=json.dumps(body.metrics, ensure_ascii=False),
        target=json.dumps(body.target.model_dump(exclude_none=True), ensure_ascii=False),
        children=json.dumps([c.model_dump(exclude_none=True) for c in (body.children or [])], ensure_ascii=False),
    )
    text, model_used = await invoke_text(prompt, fallback=_rule_based_report(body.metrics), model=body.model)

    embedding, embedding_model, failed = await apply_embedding(
        job_id, text, body.embeddingModel, body.embed, generate_embedding=generate_embedding
    )
    if failed:
        return

    response = PowerReportResponse(
        energyId=body.target.id,
        period=body.period,
        periodStart=body.periodStart,
        deviceId=body.deviceId,
        reportText=text,
        embedding=embedding,
        model=model_used,
        embeddingModel=embedding_model,
    )
    job_store.complete(job_id, response.model_dump())
