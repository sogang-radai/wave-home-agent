"""Mock implementation of docs/api.md §2.4/§2.5 routine-task tools.

Distinct from the legacy app/tools/schedule_api.py (old /api/v1/agent/* shape) —
this module matches the /internal/v1/routine-tasks contract's routine/event
type discriminator.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from app.clients.core import CoreApiClient
from app.config import get_settings


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


_MOCK_ROUTINE_TASKS: list[dict[str, Any]] = [
    {
        "id": 501,
        "type": "routine",
        "title": "운동",
        "dayOfWeek": "mon",
        "category": "exercise",
        "startMinute": 1260,
        "endMinute": 1290,
        "done": False,
    }
]

_MOCK_EVENTS: list[dict[str, Any]] = [
    {
        "id": 12,
        "type": "event",
        "title": "병원 예약",
        "date": "2026-07-06",
        "category": "posture",
        "startMinute": 1140,
        "endMinute": 1170,
        "done": False,
    }
]


async def get_routine_tasks(
    user_id: int,
    day_of_week: Optional[str] = None,
    date: Optional[str] = None,
) -> list[dict[str, Any]]:
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        items = list(_MOCK_ROUTINE_TASKS) if day_of_week is None else [
            t for t in _MOCK_ROUTINE_TASKS if t["dayOfWeek"] == day_of_week
        ]
        if date is not None:
            items += [e for e in _MOCK_EVENTS if e["date"] == date]
        return items
    params: dict[str, Any] = {}
    if day_of_week is not None:
        params["dayOfWeek"] = day_of_week
    if date is not None:
        params["date"] = date
    return await client.get(f"/users/{user_id}/routine-tasks", params)


async def update_routine_task(
    task_id: int,
    type: Literal["routine", "event"],
    reason: str,
    **fields: Any,
) -> dict[str, Any]:
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        return {"id": task_id, "type": type, "status": "ok", "updatedAt": _now_str(), **fields}
    return await client.post(f"/routine-tasks/{task_id}", json={"type": type, "reason": reason, **fields})
