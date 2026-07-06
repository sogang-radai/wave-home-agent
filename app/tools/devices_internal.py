"""Mock implementation of docs/api.md §2.2/§2.3 device tools.

Distinct from the legacy app/tools/device_api.py (old /api/v1/agent/* shape) —
this module matches the /internal/v1/devices contract's controls[] shape.
"""

from datetime import datetime, timezone
from typing import Any

from app.clients.core import CoreApiClient
from app.config import get_settings


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


_MOCK_DEVICES: list[dict[str, Any]] = [
    {
        "id": 7714208883279181,
        "name": "거실 에어컨",
        "roomId": 2,
        "class": "tuya_ep2h",
        "controls": [
            {"id": 1, "label": "온도", "type": "number", "currentValue": 24, "min": 18, "max": 30, "unit": "C"},
            {"id": 2, "label": "전원", "type": "boolean", "currentValue": True},
        ],
    },
    {
        "id": 7714208883279182,
        "name": "거실 조명",
        "roomId": 2,
        "class": "tuya_light",
        "controls": [
            {"id": 3, "label": "전원", "type": "boolean", "currentValue": True},
        ],
    },
]


async def list_devices(room_id: int, user_id: int) -> list[dict[str, Any]]:
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        return [device for device in _MOCK_DEVICES if device["roomId"] == room_id]
    return await client.get("/devices", {"roomId": room_id, "userId": user_id})


async def control_device(device_id: int, control_id: int, value: Any, user_id: int, reason: str) -> dict[str, Any]:
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        return {
            "status": "ok",
            "deviceId": device_id,
            "controlId": control_id,
            "value": value,
            "appliedAt": _now_str(),
        }
    return await client.post(
        f"/devices/{device_id}/controls/{control_id}",
        json={"value": value, "userId": user_id, "reason": reason},
    )
