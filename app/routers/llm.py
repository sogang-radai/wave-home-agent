import json
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients.ollama import OllamaClient, OllamaError
from app.errors import AgentApiError
from app.schemas.llm import ChatCompletionRequest, EmbeddingRequest, LlmModel, LlmModelList


router = APIRouter(prefix="/llm/v1", tags=["llm"])


def _map_error(exc: OllamaError) -> AgentApiError:
    if exc.status_code == 404:
        return AgentApiError(404, "MODEL_NOT_FOUND", "지원하지 않는 model 입니다. /models 로 사용 가능한 모델을 조회하세요.")
    if exc.is_timeout:
        return AgentApiError(504, "LLM_TIMEOUT", "LLM 응답 생성 시간이 초과되었습니다.")
    return AgentApiError(502, "LLM_PROVIDER_ERROR", "LLM 제공자 응답을 처리하지 못했습니다.")


@router.get("/models", response_model=LlmModelList)
async def list_models() -> LlmModelList:
    client = OllamaClient()
    try:
        tags = await client.get("/api/tags")
    except OllamaError as exc:
        raise _map_error(exc) from exc

    models = []
    for entry in tags.get("models", []):
        capabilities = entry.get("capabilities", [])
        role = "embedding" if "embedding" in capabilities else "chat"
        dimension = entry.get("details", {}).get("embedding_length") if role == "embedding" else None
        models.append(LlmModel(id=entry["name"], role=role, provider="ollama", dimension=dimension))
    return LlmModelList(data=models)


@router.post("/chat/completions", response_model=None)
async def chat_completions(body: ChatCompletionRequest):
    client = OllamaClient()
    payload = body.model_dump(exclude_none=True)

    if body.stream:
        return StreamingResponse(
            _stream_chat_completions(client, payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        response = await client.post("/v1/chat/completions", payload)
    except OllamaError as exc:
        raise _map_error(exc) from exc
    return JSONResponse(content=response)


async def _stream_chat_completions(client: OllamaClient, payload: dict[str, Any]) -> AsyncIterator[bytes]:
    try:
        async for chunk in client.stream_post("/v1/chat/completions", payload):
            yield chunk
    except OllamaError as exc:
        error = _map_error(exc)
        payload_out = {"error": {"code": error.code, "message": error.message}}
        yield f"data: {json.dumps(payload_out, ensure_ascii=False)}\n\n".encode()


@router.post("/embeddings", response_model=None)
async def embeddings(body: EmbeddingRequest):
    if not body.input:
        raise AgentApiError(400, "INVALID_REQUEST", "input 은 비어 있을 수 없습니다.", field="input")

    client = OllamaClient()
    try:
        response = await client.post("/v1/embeddings", body.model_dump())
    except OllamaError as exc:
        raise _map_error(exc) from exc
    return JSONResponse(content=response)
