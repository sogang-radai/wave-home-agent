from typing import Any, Optional

from app.clients.core import CoreApiClient


async def get_posture_summary(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    client = CoreApiClient()
    if client.is_mock:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "score": 72,
            "average_score": 70,
            "correct_posture_percent": 68,
            "total_sitting_minutes": 320,
            "max_continuous_sitting_minutes": 37,
            "turtle_neck_count": 5,
            "trend": "slightly_worse",
        }
    return await client.get(
        f"/api/v1/accounts/{user_id}/posture/summary",
        {"start": start_date, "end": end_date},
    )
