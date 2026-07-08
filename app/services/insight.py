"""insight-generation-api.md 비즈니스 로직: 배치 인사이트 생성을 job 으로 처리한다.

app/services/job_common.py 의 공용 job 골격(create_job_or_409/spawn/apply_embedding)을
sleep/power 와 동일하게 재사용한다.
"""

import logging

from app.graph.insight_graph import build as build_insight_graph
from app.schemas.insight import InsightGenerationRequest
from app.schemas.jobs import JobRef
from app.services.embeddings import generate_embedding
from app.services.job_common import apply_embedding, create_job_or_409, spawn
from app.services.jobs import job_store


logger = logging.getLogger(__name__)

INSIGHT_KIND = "insight_generation"

_graph = build_insight_graph()


def create_insight_job(body: InsightGenerationRequest) -> JobRef:
    dedupe_key = f"{INSIGHT_KIND}:{body.userId}:{body.surface}:{body.date}"
    job = create_job_or_409(INSIGHT_KIND, dedupe_key=dedupe_key)
    spawn(_run_generation(job.job_id, body))
    return JobRef(jobId=job.job_id)


async def _run_generation(job_id: str, body: InsightGenerationRequest) -> None:
    job_store.mark_running(job_id)
    result = await _graph.ainvoke(
        {
            "user_id": body.userId,
            "surface": body.surface,
            "date": body.date,
            "context": body.context,
            "rounds": 0,
        }
    )
    items = result.get("items", [])

    if body.embed:
        for item in items:
            text = f"{item['title']}\n{item['text']}"  # rag-api.md: title + "\n" + text
            embedding, _embedding_model, failed = await apply_embedding(
                job_id, text, None, True, generate_embedding=generate_embedding
            )
            if failed:
                return
            item["embedding"] = embedding

    job_store.complete(job_id, {"items": items})
