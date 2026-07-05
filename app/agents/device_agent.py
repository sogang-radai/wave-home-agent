from typing import Any

from app.clients.core import ToolError
from app.models.action import ActionResult
from app.state.agent_state import AgentState
from app.tools.device_api import control_device, get_device_status


async def run(state: AgentState) -> dict[str, Any]:
    plan = state["action_plan"]
    target = plan.get("target", {})
    device_id = target.get("device_id")
    control_id = target.get("control_id", "power")
    value = target.get("value")

    try:
        await control_device(device_id, control_id, value)
        devices = await get_device_status(state["user_id"])
    except ToolError:
        result = ActionResult(status="failed", detail="가전 제어에 실패했습니다.")
        return {"action_result": result.model_dump()}

    updated = next((device for device in devices if device.get("id") == device_id), None)
    if updated is None:
        result = ActionResult(status="failed", detail="제어한 기기 상태를 확인하지 못했습니다.")
    else:
        result = ActionResult(
            status="ok",
            detail=f"'{updated.get('name', device_id)}' 상태를 '{updated.get('state')}'(으)로 확인했습니다.",
        )
    return {"action_result": result.model_dump()}
