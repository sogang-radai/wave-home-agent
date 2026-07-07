"""docs/api.md §1.4 Power Analysis API business logic. Mirrors app/services/sleep_analysis.py."""

import asyncio
import json
import logging
from typing import Any

from app.errors import AgentApiError
from app.schemas.jobs import JobRef
from app.schemas.power_analysis import PowerReportRequest, PowerReportResponse
from app.services.embeddings import EmbeddingError, generate_embedding
from app.services.jobs import JobAlreadyRunning, job_store
from app.services.llm import invoke_text
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

REPORT_KIND = "power_report"

_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _rule_based_report(metrics: dict[str, Any]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in metrics.items()) or "제공된 지표가 없습니다."


async def _apply_embedding(job_id: str, text: str, requested_model: str | None, embed: bool) -> tuple[Any, Any, bool]:
    if not embed:
        return None, None, False
    try:
        embedding, embedding_model = await generate_embedding(text, requested_model)
        return embedding, embedding_model, False
    except EmbeddingError as exc:
        code = "GENERATION_TIMEOUT" if exc.is_timeout else "GENERATION_FAILED"
        message = "임베딩 생성 시간이 초과되었습니다." if exc.is_timeout else "임베딩 생성에 실패했습니다."
        job_store.fail(job_id, {"code": code, "message": message})
        return None, None, True


def create_report_job(body: PowerReportRequest) -> JobRef:
    if body.target.granularity != body.period:
        raise AgentApiError(
            400,
            "INVALID_REQUEST",
            "target.granularity 는 리포트 대상(1h/24h/1w/1mo)이어야 합니다.",
            field="target.granularity",
        )

    try:
        job = job_store.create(REPORT_KIND, dedupe_key=f"{REPORT_KIND}:{body.target.id}")
    except JobAlreadyRunning as exc:
        raise AgentApiError(
            409,
            "JOB_ALREADY_RUNNING",
            "동일 energyId(target.id)에 대한 job 이 이미 queued/running 상태입니다.",
            detail={"jobId": exc.existing_job_id},
        ) from exc

    _spawn(_run_report(job.job_id, body))
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

    embedding, embedding_model, failed = await _apply_embedding(job_id, text, body.embeddingModel, body.embed)
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
