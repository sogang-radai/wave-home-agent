from typing import Any

from app.clients.core import ToolError
from app.models.action import ActionResult
from app.state.agent_state import AgentState
from app.tools.schedule_api import get_schedule, update_schedule


async def run(state: AgentState) -> dict[str, Any]:
    plan = state["action_plan"]
    target = plan.get("target", {})
    task_id = target.get("task_id")
    changes = target.get("changes", {})

    try:
        await update_schedule(state["user_id"], task_id, changes)
        schedule = await get_schedule(state["user_id"])
    except ToolError:
        result = ActionResult(status="failed", detail="일정 변경에 실패했습니다.")
        return {"action_result": result.model_dump()}

    updated = next((task for task in schedule if task.get("id") == task_id), None)
    if updated is None:
        result = ActionResult(status="failed", detail="변경한 일정을 확인하지 못했습니다.")
    else:
        result = ActionResult(status="ok", detail=f"'{updated.get('title', task_id)}' 일정을 변경했습니다.")
    return {"action_result": result.model_dump()}
