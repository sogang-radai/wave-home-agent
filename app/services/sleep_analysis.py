"""docs/api.md §1.4 Sleep Analysis API business logic: validates requests, enqueues a
background job (app/services/jobs.py), generates summaryText/reportText via LLM with a
rule-based fallback (mirrors app/graph/report_turn_graph.py's _rule_based_content), and
optionally an embedding via Ollama (app/services/embeddings.py)."""

import json
import logging
from typing import Any

from app.errors import AgentApiError
from app.schemas.jobs import JobRef
from app.schemas.sleep_analysis import (
    SleepReportRequest,
    SleepReportResponse,
    SleepSummaryRequest,
    SleepSummaryResponse,
)
from app.services.embeddings import generate_embedding
from app.services.job_common import apply_embedding, create_job_or_409, spawn
from app.services.jobs import job_store
from app.services.llm import invoke_text
from app.services.prompts import load_prompt


logger = logging.getLogger(__name__)

SUMMARY_KIND = "sleep_summary"
REPORT_KIND = "sleep_report"


def _rule_based_summary(body: SleepSummaryRequest) -> str:
    fields = body.window.model_dump(exclude_none=True, exclude={"id", "userId", "roomId", "sessionId"})
    return "; ".join(f"{k}: {v}" for k, v in fields.items()) or "제공된 통계가 없습니다."


def _rule_based_report(metrics: dict[str, Any]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in metrics.items()) or "제공된 지표가 없습니다."


def create_summary_job(body: SleepSummaryRequest) -> JobRef:
    if body.window.granularity != "30m":
        raise AgentApiError(
            400, "INVALID_WINDOW", "window.granularity 는 30m 이어야 합니다.", field="window.granularity"
        )

    job = create_job_or_409(SUMMARY_KIND, dedupe_key=f"{SUMMARY_KIND}:{body.window.id}")
    spawn(_run_summary(job.job_id, body))
    return JobRef(jobId=job.job_id)


async def _run_summary(job_id: str, body: SleepSummaryRequest) -> None:
    job_store.mark_running(job_id)
    prompt = load_prompt(
        "sleep",
        "summary",
        window=json.dumps(body.window.model_dump(exclude_none=True), ensure_ascii=False),
        minutes=json.dumps([m.model_dump(exclude_none=True) for m in (body.minutes or [])], ensure_ascii=False),
    )
    text, model_used = await invoke_text(prompt, fallback=_rule_based_summary(body), model=body.model)

    embedding, embedding_model, failed = await apply_embedding(
        job_id, text, body.embeddingModel, body.embed, generate_embedding=generate_embedding
    )
    if failed:
        return

    response = SleepSummaryResponse(
        statId=body.window.id,
        summaryText=text,
        embedding=embedding,
        model=model_used,
        embeddingModel=embedding_model,
    )
    job_store.complete(job_id, response.model_dump())


def create_report_job(body: SleepReportRequest) -> JobRef:
    if not body.sessions:
        raise AgentApiError(
            400,
            "NO_SLEEP_DATA",
            "sessions 가 비어 있습니다. 해당 기간 수면 데이터를 먼저 조회해 Body 를 구성하세요.",
            field="sessions",
        )
    if body.period == "weekly":
        from datetime import date

        parsed = date.fromisoformat(body.periodStart)
        if parsed.weekday() != 0:
            raise AgentApiError(
                400, "INVALID_WEEK_START", "weekStart는 해당 주의 월요일 날짜여야 합니다.", field="periodStart"
            )

    dedupe_key = f"{REPORT_KIND}:{body.userId}:{body.period}:{body.periodStart}"
    job = create_job_or_409(REPORT_KIND, dedupe_key=dedupe_key)
    spawn(_run_report(job.job_id, body))
    return JobRef(jobId=job.job_id)


async def _run_report(job_id: str, body: SleepReportRequest) -> None:
    job_store.mark_running(job_id)
    prompt = load_prompt(
        "sleep",
        "report",
        period=body.period,
        period_start=body.periodStart,
        metrics=json.dumps(body.metrics, ensure_ascii=False),
        sessions=json.dumps([s.model_dump(exclude_none=True) for s in body.sessions], ensure_ascii=False),
        stats30m=json.dumps([s.model_dump(exclude_none=True) for s in body.stats30m], ensure_ascii=False),
    )
    text, model_used = await invoke_text(prompt, fallback=_rule_based_report(body.metrics), model=body.model)

    embedding, embedding_model, failed = await apply_embedding(
        job_id, text, body.embeddingModel, body.embed, generate_embedding=generate_embedding
    )
    if failed:
        return

    response = SleepReportResponse(
        period=body.period,
        periodStart=body.periodStart,
        reportText=text,
        embedding=embedding,
        model=model_used,
        embeddingModel=embedding_model,
    )
    job_store.complete(job_id, response.model_dump())
