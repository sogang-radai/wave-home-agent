from typing import Any, Literal

from pydantic import BaseModel, Field


ActionType = Literal["schedule_update", "device_control"]
ActionStatus = Literal["planned", "ok", "failed"]


class ActionPlan(BaseModel):
    type: ActionType
    description: str
    target: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    status: ActionStatus
    detail: str
