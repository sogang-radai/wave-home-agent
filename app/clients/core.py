import logging
from typing import Any, Optional

import httpx

from app.clients.demo_context import get_demo_runtime_id
from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Raised when a call to the C++ backend fails after retrying.

    code/status_code/detail carry the backend's {error:{code,message,field?,detail?}}
    body (device-tool-api.md/db-query-api.md/etc §공통 에러) when available, so callers
    (app/tools/*_internal.py) can re-wrap them into a structured InternalApiError instead
    of a bare string.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.detail = detail


def _parse_error_body(response: httpx.Response) -> Optional[dict[str, Any]]:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"]
    return None


def _preview(value: Any, limit: int = 500) -> str:
    """Renders a request/response payload for a single-line log entry, capped
    so a large device/rule list doesn't blow up the log."""
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}...(truncated)"


class CoreApiClient:
    """Generic transport for the C++ server that owns SQLite and device/schedule state.

    Domain-specific shape and mock fixtures live in app/tools/*_api.py; this
    class only knows HTTP, retry, and logging (interface.md #13).
    """

    def __init__(self, settings: Optional[Settings] = None, *, base_url: Optional[str] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = (base_url or self.settings.wavehome_core_api_base_url).rstrip("/")
        self.timeout = self.settings.wavehome_core_api_timeout_ms / 1000

    @property
    def is_mock(self) -> bool:
        return self.settings.wavehome_core_api_mock

    async def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("POST", path, json=json)

    async def put(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("DELETE", path, params=params)

    async def patch(self, path: str, json: Optional[dict[str, Any]] = None, params: Optional[dict[str, Any]] = None) -> Any:
        return await self._request("PATCH", path, json=json, params=params)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        demo_runtime_id = get_demo_runtime_id()
        if demo_runtime_id:
            headers = dict(kwargs.get("headers") or {})
            headers["X-Wave-Demo-Runtime-Id"] = demo_runtime_id
            kwargs["headers"] = headers
            if method in {"POST", "PUT", "PATCH"}:
                payload = dict(kwargs.get("json") or {})
                payload.setdefault("demoRuntimeId", demo_runtime_id)
                kwargs["json"] = payload
        # schedule-tasks-api.md/alarms-api.md 의 GET 은 봉투 없이 배열을 바로 반환하므로
        # 반환 타입을 dict 로 좁히지 않는다(device-tool-api.md 의 {items,count} 봉투와 공존).
        last_error: Optional[Exception] = None
        for attempt in (1, 2):
            logger.info(
                "core api -> %s %s%s params=%s json=%s (attempt %d/2)",
                method, self.base_url, path, kwargs.get("params"), _preview(kwargs.get("json")), attempt,
            )
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                    response = await client.request(method, path, **kwargs)
                    response.raise_for_status()
                    body = response.json()
                    logger.info(
                        "core api <- %s %s%s %d body=%s",
                        method, self.base_url, path, response.status_code, _preview(body),
                    )
                    return body
            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "core api <- %s %s%s %d body=%s",
                    method, self.base_url, path, exc.response.status_code, _preview(exc.response.text),
                )
                parsed = _parse_error_body(exc.response)
                if 400 <= exc.response.status_code < 500:
                    # 4xx 는 재시도해도 결과가 바뀌지 않는다(DEVICE_OFFLINE/NOT_FOUND 등) — 즉시 raise.
                    if parsed is not None:
                        raise ToolError(
                            parsed.get("message", f"{method} {path} failed"),
                            code=parsed.get("code"),
                            status_code=exc.response.status_code,
                            detail=parsed.get("detail"),
                        ) from exc
                    raise ToolError(
                        f"{method} {path} failed ({exc.response.status_code})",
                        status_code=exc.response.status_code,
                    ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Core API %s %s failed (attempt %d/2)", method, path, attempt, exc_info=True)
        raise ToolError(f"{method} {path} failed") from last_error
