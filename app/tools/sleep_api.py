from typing import Any, Optional

from app.clients.core import CoreApiClient


async def get_sleep_summary(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    client = CoreApiClient()
    if client.is_mock:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "score": 78,
            "average_score": 74,
            "actual_sleep_minutes": 415,
            "time_in_bed_minutes": 450,
            "wake_ups": 3,
            "avg_sleep_minutes": 402,
            "trend": "slightly_worse",
        }
    return await client.get(
        f"/api/v1/accounts/{user_id}/sleep/summary",
        {"start": start_date, "end": end_date},
    )
