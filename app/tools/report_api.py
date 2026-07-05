from datetime import date, timedelta
from typing import Any

from app.tools.posture_api import get_posture_summary
from app.tools.sleep_api import get_sleep_summary


async def get_report_context(user_id: str, report_type: str) -> dict[str, Any]:
    today = date.today()
    week_start = today - timedelta(days=7)

    if report_type == "weekly_sleep_report":
        sleep = await get_sleep_summary(user_id, week_start.isoformat(), today.isoformat())
        return {"sleep": sleep}
    if report_type == "nightly_sleep_report":
        sleep = await get_sleep_summary(user_id, today.isoformat(), today.isoformat())
        return {"sleep": sleep}
    if report_type == "weekly_posture_report":
        posture = await get_posture_summary(user_id, week_start.isoformat(), today.isoformat())
        return {"posture": posture}
    if report_type == "daily_posture_report":
        posture = await get_posture_summary(user_id, today.isoformat(), today.isoformat())
        return {"posture": posture}
    raise ValueError(f"Unsupported report_type: {report_type}")
