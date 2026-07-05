from typing import Any, Optional


async def get_observation_summary(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Mock-only: docs/db.md has no camera/observation-event table yet.

    device.class includes 'wave_cam' but there is no backing event log, so
    there is no real C++ endpoint to call here. Replace this with a real
    CoreApiClient call once that API exists.
    """
    return {
        "start_date": start_date,
        "end_date": end_date,
        "activity_level": "normal",
        "night_activity_events": 1,
        "notes": ["자정 이후 거실에서 짧은 움직임이 감지되었습니다."],
    }
