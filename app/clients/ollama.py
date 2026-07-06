import logging
from typing import Any, AsyncIterator, Optional

import httpx

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised on any failure talking to Ollama's OpenAI-compatible /v1/* API.

    Carries enough detail for app/routers/llm.py to map onto docs/api.md §1.3's error codes:
    status_code=404 -> MODEL_NOT_FOUND, is_timeout -> LLM_TIMEOUT, otherwise -> LLM_PROVIDER_ERROR.
    """

    def __init__(self, message: str, *, is_timeout: bool = False, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.is_timeout = is_timeout
        self.status_code = status_code


class OllamaClient:
    """Thin transport to Ollama, distinct from CoreApiClient (app/clients/core.py):
    that one retries-then-raises a single ToolError, but callers here need to distinguish
    timeout vs. connection failure vs. upstream 4xx (e.g. unknown model)."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.ollama_base_url.rstrip("/")
        self.timeout = self.settings.ollama_timeout_ms / 1000

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise OllamaError(f"{method} {path} timed out", is_timeout=True) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"{method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            raise OllamaError(
                f"{method} {path} failed with {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        return response.json()

    async def stream_post(self, path: str, json: dict[str, Any]) -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                async with client.stream("POST", path, json=json) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise OllamaError(
                            f"POST {path} failed with {response.status_code}: {body.decode(errors='replace')}",
                            status_code=response.status_code,
                        )
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except httpx.TimeoutException as exc:
            raise OllamaError(f"POST {path} timed out", is_timeout=True) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"POST {path} failed: {exc}") from exc
