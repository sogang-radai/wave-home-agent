from typing import Any

from app.clients.core import CoreApiClient


async def get_device_status(user_id: str) -> list[dict[str, Any]]:
    client = CoreApiClient()
    if client.is_mock:
        return [
            {"id": "light_living_room", "name": "거실 조명", "state": "on"},
            {"id": "ac_bedroom", "name": "침실 에어컨", "state": "24C"},
        ]
    return await client.get(f"/api/v1/accounts/{user_id}/devices")


async def control_device(device_id: str, control_id: str, value: Any) -> dict[str, Any]:
    client = CoreApiClient()
    if client.is_mock:
        return {"status": "mocked", "device_id": device_id, "control_id": control_id, "value": value}
    return await client.post(
        f"/api/v1/devices/{device_id}/controls/{control_id}",
        json={"value": value},
    )
