"""app/services/{sleep,power}_analysis.py 에 동일하게 복붙돼 있던 job 골격
(_spawn, _apply_embedding, JobAlreadyRunning->409 변환, GET /jobs/{id} 응답 조립)을
추출한 공용 모듈. insight/weekly_plan 서비스도 이걸 재사용한다.

generate_embedding 은 파라미터로 주입받는다(기본값 바인딩 X) — 각 호출부가
자기 모듈에 `from app.services.embeddings import generate_embedding` 로 남겨둔
이름을 그대로 넘기게 해서, tests/conftest.py 의
monkeypatch.setattr("app.services.sleep_analysis.generate_embedding", ...) 같은
모듈 한정 patch 타깃이 리팩터 후에도 그대로 유효하도록 만들기 위함이다.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from fastapi.responses import JSONResponse

from app.errors import AgentApiError
from app.services.embeddings import EmbeddingError
from app.services.jobs import Job, JobAlreadyRunning, job_store


logger = logging.getLogger(__name__)

GenerateEmbeddingFn = Callable[[str, Optional[str]], Awaitable[tuple[Any, str]]]

_background_tasks: set[asyncio.Task] = set()


async def _run_guarded(job_id: str, coro: Awaitable[None]) -> None:
    """spawn() 이 백그라운드 태스크로 도는 job 코루틴을 감싸는 최후의 안전망.

    각 _run_* 함수 내부(invoke_text/invoke_structured, apply_embedding)는 이미 알려진
    실패를 잡아 job_store.fail 을 부르지만, tool_loop.py의 gather 노드가 쓰는 LLM 호출
    (app/graph/tool_loop.py 의 agent_node 안 bound.ainvoke)처럼 try/except 로 안 감싸인
    지점에서 예외가 나면 아무도 job_store.fail/complete 를 안 불러서 job 이 영원히
    "running" 상태로 멈춰버린다(클라이언트는 폴링만 계속하게 됨). 여기서 잡아서
    반드시 done/failed 로 끝나게 만든다."""
    try:
        await coro
    except Exception:
        logger.exception("job crashed with an unhandled exception: id=%s", job_id)
        job_store.fail(job_id, {"code": "GENERATION_FAILED", "message": "요청 처리 중 오류가 발생했습니다."})


def spawn(coro: Awaitable[None], *, job_id: Optional[str] = None) -> None:
    if job_id is not None:
        coro = _run_guarded(job_id, coro)
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def create_job_or_409(kind: str, dedupe_key: str) -> Job:
    try:
        return job_store.create(kind, dedupe_key=dedupe_key)
    except JobAlreadyRunning as exc:
        raise AgentApiError(
            409,
            "JOB_ALREADY_RUNNING",
            "동일 대상에 대한 job 이 이미 queued/running 상태입니다.",
            job_id=exc.existing_job_id,
        ) from exc


async def apply_embedding(
    job_id: str,
    text: str,
    requested_model: Optional[str],
    embed: bool,
    *,
    generate_embedding: GenerateEmbeddingFn,
) -> tuple[Any, Any, bool]:
    """Returns (embedding, embeddingModel, failed). 실패 시 이미 job_store.fail 호출됨 —
    호출자는 failed=True 면 즉시 return 해야 한다(job.complete 를 부르면 안 됨)."""
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


def get_job_or_404(job_id: str, kinds: set[str]) -> Job:
    job = job_store.get(job_id, kinds=kinds)
    if job is None:
        raise AgentApiError(404, "JOB_NOT_FOUND", "jobId 에 해당하는 작업이 없습니다.")
    return job


def job_response(job: Job) -> JSONResponse:
    payload: dict[str, Any] = {"jobId": job.job_id, "status": job.status}
    if job.result is not None:
        payload["result"] = job.result
    if job.error is not None:
        payload["error"] = job.error
    return JSONResponse(content=payload)