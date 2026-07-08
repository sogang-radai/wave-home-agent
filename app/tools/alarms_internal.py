"""alarms-api.md 의 알람 설정 CRUD(`/internal/v1/alarms`) 클라이언트.

`GET` 응답은 봉투 없이 배열을 바로 반환한다(schedule-tasks-api.md 와 동일 패턴,
device-tool-api.md 의 {items,count} 봉투와 다름 — 주의). `deviceId`/`radarDeviceId`
는 이 모듈의 시그니처에서는 int, wire 상 16자리 hex 변환은 호출 경계에서만.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel

from app.clients.core import CoreApiClient, ToolError
from app.config import get_settings
from app.tools.device_id import device_id_to_hex_or_none, hex_to_device_id_or_none
from app.tools.errors import InternalApiError
from app.tools.schedule_tasks_internal import DayOfWeek


class AlarmMethodLightBlink(BaseModel):
    type: Literal["light_blink"] = "light_blink"
    brightness: int
    intervalSec: int


class AlarmMethodLightOn(BaseModel):
    type: Literal["light_on"] = "light_on"
    brightness: int


class AlarmMethodPlugToggle(BaseModel):
    type: Literal["plug_toggle"] = "plug_toggle"


class AlarmMethodPlugOn(BaseModel):
    type: Literal["plug_on"] = "plug_on"


class AlarmMethodPlugOff(BaseModel):
    type: Literal["plug_off"] = "plug_off"


class AlarmMethodTts(BaseModel):
    type: Literal["tts"] = "tts"
    speakerId: int
    text: str
    repeatCount: int
    intervalSec: int


AlarmMethod = Union[
    AlarmMethodLightBlink,
    AlarmMethodLightOn,
    AlarmMethodPlugToggle,
    AlarmMethodPlugOn,
    AlarmMethodPlugOff,
    AlarmMethodTts,
]


class Alarm(BaseModel):
    id: int
    userId: int
    name: str
    timeMinute: int
    daysOfWeek: list[DayOfWeek] = []
    smartWake: bool = False
    radarDeviceId: Optional[int] = None
    deviceId: Optional[int] = None
    method: Optional[AlarmMethod] = None
    enabled: bool = True
    createdAt: str
    updatedAt: str


class CreateAlarmRequest(BaseModel):
    userId: int
    name: str
    timeMinute: int
    daysOfWeek: list[DayOfWeek] = []
    smartWake: bool = False
    radarDeviceId: Optional[int] = None
    deviceId: Optional[int] = None
    method: Optional[AlarmMethod] = None
    enabled: bool = True


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _client() -> CoreApiClient:
    return CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)


def _raise_from_tool_error(exc: ToolError) -> None:
    raise InternalApiError(exc.code or "CORE_API_UNAVAILABLE", str(exc), detail=exc.detail) from exc


def _alarm_to_wire(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    if "radarDeviceId" in data:
        data["radarDeviceId"] = device_id_to_hex_or_none(data["radarDeviceId"])
    if "deviceId" in data:
        data["deviceId"] = device_id_to_hex_or_none(data["deviceId"])
    return data


def _alarm_from_wire(item: dict[str, Any]) -> Alarm:
    item = dict(item)
    item["radarDeviceId"] = hex_to_device_id_or_none(item.get("radarDeviceId"))
    item["deviceId"] = hex_to_device_id_or_none(item.get("deviceId"))
    return Alarm.model_validate(item)


# ── mock 상태 (WAVEHOME_CORE_API_MOCK=true) ─────────────────────────────────

_MOCK_ALARMS: list[Alarm] = [
    Alarm(
        id=1,
        userId=1,
        name="평일 기상",
        timeMinute=420,
        daysOfWeek=["mon", "tue", "wed", "thu", "fri"],
        smartWake=True,
        radarDeviceId=7714208883279181,
        deviceId=7714208883279181,
        method=AlarmMethodTts(speakerId=0, text="좋은 아침이에요!", repeatCount=3, intervalSec=20),
        enabled=True,
        createdAt="2026-06-01 09:00:00",
        updatedAt="2026-06-01 09:00:00",
    )
]

_next_mock_id = 2


async def get_alarms(user_id: int, *, enabled: Optional[bool] = None) -> list[Alarm]:
    client = _client()
    if client.is_mock:
        items = [a for a in _MOCK_ALARMS if a.userId == user_id]
        if enabled is not None:
            items = [a for a in items if a.enabled == enabled]
        return sorted(items, key=lambda a: a.timeMinute)

    params = {k: v for k, v in {"userId": user_id, "enabled": enabled}.items() if v is not None}
    try:
        response = await client.get("/alarms", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [_alarm_from_wire(item) for item in response]


async def create_alarm(req: CreateAlarmRequest) -> Alarm:
    client = _client()
    if client.is_mock:
        global _next_mock_id
        alarm = Alarm(id=_next_mock_id, createdAt=_now_str(), updatedAt=_now_str(), **req.model_dump())
        _next_mock_id += 1
        _MOCK_ALARMS.append(alarm)
        return alarm

    try:
        response = await client.post("/alarms", json=_alarm_to_wire(req.model_dump(exclude_none=True)))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _alarm_from_wire(response)


async def update_alarm(alarm_id: int, user_id: int, **fields: Any) -> Alarm:
    client = _client()
    if client.is_mock:
        for idx, alarm in enumerate(_MOCK_ALARMS):
            if alarm.id == alarm_id and alarm.userId == user_id:
                updated = alarm.model_copy(update={**fields, "updatedAt": _now_str()})
                _MOCK_ALARMS[idx] = updated
                return updated
        raise InternalApiError("NOT_FOUND", f"id={alarm_id} 인 알람을 찾을 수 없습니다.")

    try:
        response = await client.patch(f"/alarms/{alarm_id}", json=_alarm_to_wire(fields), params={"userId": user_id})
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _alarm_from_wire(response)


async def delete_alarm(alarm_id: int, user_id: int) -> int:
    client = _client()
    if client.is_mock:
        before = len(_MOCK_ALARMS)
        _MOCK_ALARMS[:] = [a for a in _MOCK_ALARMS if not (a.id == alarm_id and a.userId == user_id)]
        if len(_MOCK_ALARMS) == before:
            raise InternalApiError("NOT_FOUND", f"id={alarm_id} 인 알람을 찾을 수 없습니다.")
        return alarm_id

    try:
        response = await client.delete(f"/alarms/{alarm_id}", params={"userId": user_id})
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return int(response["id"])
