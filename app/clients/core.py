from typing import Any, Optional

import httpx

from app.config import Settings, get_settings


class CoreApiClient:
    """Client for the C++ server that owns SQLite and device/schedule state."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.wavehome_core_api_base_url.rstrip("/")
        self.timeout = self.settings.wavehome_core_api_timeout_ms / 1000

    async def get_context(
        self,
        *,
        account_id: str,
        task: str,
        user_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if self.settings.wavehome_core_api_mock:
            return self._mock_context(
                account_id=account_id,
                task=task,
                user_message=user_message,
            )

        payload = {
            "accountId": account_id,
            "task": task,
            "userMessage": user_message,
            "metadata": metadata or {},
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/v1/agent/context", json=payload)
            response.raise_for_status()
            return response.json()

    async def request_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if self.settings.wavehome_core_api_mock:
            return {"status": "mocked", "action": action}

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/v1/agent/actions", json=action)
            response.raise_for_status()
            return response.json()

    def _mock_context(
        self,
        *,
        account_id: str,
        task: str,
        user_message: Optional[str],
    ) -> dict[str, Any]:
        return {
            "accountId": account_id,
            "task": task,
            "userMessage": user_message,
            "sleep": {
                "lastNight": {
                    "durationMinutes": 415,
                    "quality": "fair",
                    "wakeUps": 3,
                },
                "weeklyAverageMinutes": 402,
            },
            "posture": {
                "today": {
                    "goodPostureRatio": 0.68,
                    "longestBadPostureMinutes": 37,
                },
                "weeklyTrend": "slightly_worse",
            },
            "devices": [
                {"id": "light_living_room", "name": "거실 조명", "state": "on"},
                {"id": "ac_bedroom", "name": "침실 에어컨", "state": "24C"},
            ],
            "schedule": [
                {"id": "task_exercise_tonight", "title": "운동", "time": "오늘 21:00"},
            ],
        }
