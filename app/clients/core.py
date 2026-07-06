import logging
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings


logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Raised when a call to the C++ backend fails after retrying."""


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

    async def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                    response = await client.request(method, path, **kwargs)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Core API %s %s failed (attempt %d/2)", method, path, attempt, exc_info=True)
        raise ToolError(f"{method} {path} failed") from last_error
