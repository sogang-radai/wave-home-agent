from typing import Any

from app.clients.core import CoreApiClient


async def get_schedule(user_id: str) -> list[dict[str, Any]]:
    client = CoreApiClient()
    if client.is_mock:
        return [
            {
                "id": "task_exercise_tonight",
                "title": "운동",
                "day_of_week": "mon",
                "category": "posture",
                "start_minute": 21 * 60,
                "end_minute": 21 * 60 + 30,
                "done": False,
            }
        ]
    return await client.get(f"/api/v1/accounts/{user_id}/schedule")


async def update_schedule(user_id: str, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    client = CoreApiClient()
    if client.is_mock:
        return {"id": task_id, "status": "mocked", **changes}
    return await client.post(f"/api/v1/accounts/{user_id}/schedule/{task_id}", json=changes)
