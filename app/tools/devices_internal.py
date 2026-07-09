"""device-tool-api.md 의 장치 조회·제어 REST(`/internal/v1/devices*`) 클라이언트.

에이전트 내부(이 모듈의 시그니처, 호출부)는 항상 int deviceId 를 쓴다. device-tool-api.md
의 wire 계약은 16자리 hex 문자열이므로, httpx 호출 경계에서만 app/tools/device_id.py 로
변환한다(agent-be/db-schema.md:749 — 백엔드가 정수 id로부터 즉석에서 계산해 내려주는 값이라
별도 조회 없이 로컬 변환만으로 충분하다).

`tools/device.*` 고수준 RPC(device-tool-api.md)는 구현하지 않는다 — `/rules`·`/devices/*`
REST 를 그대로 복제한 설계이고 백엔드도 미구현이다. 대신 이 모듈이 REST 를 직접 호출하고,
roomId+장치이름 해석은 resolve_device_id() 로 처리한다(app/graph/tools.py 가 사용).
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.clients.core import CoreApiClient, ToolError
from app.config import get_settings
from app.tools.db_query import MOCK_DEVICES
from app.tools.device_id import device_id_to_hex, hex_to_device_id
from app.tools.errors import InternalApiError


ActionAttribute = Literal["Toggle", "Repeat", "Momentary", "Stateful"]
ExecMode = Literal["once", "repeat", "toggle"]


class DeviceAction(BaseModel):
    name: str
    description: str = ""
    attributes: list[ActionAttribute] = Field(default_factory=list)
    paramsSchema: dict[str, Any] = Field(default_factory=dict)


class DeviceQuery(BaseModel):
    name: str
    description: str = ""
    paramsSchema: Optional[dict[str, Any]] = None


class DeviceClassCapabilities(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    class_: str = Field(alias="class")
    label: str = ""
    actions: list[DeviceAction] = Field(default_factory=list)
    queries: list[DeviceQuery] = Field(default_factory=list)
    triggerKinds: list[Literal["gesture", "device_state", "ir_recv"]] = Field(default_factory=list)
    triggerableQueries: Optional[list[str]] = None
    ptz: Optional[bool] = None


class RoomRef(BaseModel):
    id: int
    name: str


class DeviceSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    description: str = ""
    class_: str = Field(alias="class")
    classLabel: str = ""
    vendor: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True
    connected: bool = False
    lastSeenAt: Optional[str] = None
    stateSummary: str = ""
    room: Optional[RoomRef] = None


class DeviceDetail(DeviceSummary):
    capabilities: DeviceClassCapabilities


class InvokeDeviceRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    execMode: ExecMode = "once"
    repeatIntervalMs: Optional[int] = None
    triggeredBy: Optional[str] = None


class InvokeDeviceResponse(BaseModel):
    ok: bool
    deviceId: int
    action: str
    state: dict[str, Any] = Field(default_factory=dict)
    eventId: str = ""


class QueryDeviceRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class QueryDeviceResponse(BaseModel):
    deviceId: int
    query: str
    result: dict[str, Any] = Field(default_factory=dict)


class DeviceStateSnapshot(BaseModel):
    deviceId: int
    connected: bool
    state: dict[str, Any] = Field(default_factory=dict)


# ── 카메라 PTZ / 스트림 / TTS (device-tool-api.md §카메라 PTZ / 스트림 / TTS) ─────
# ptz/{move,stop,zoom} 과 tts 의 성공 응답 바디는 문서에 예시가 없다(요청 바디만
# 명시됨) — 백엔드가 실제로 뭘 돌려주는지 확정되면 아래 dict[str, Any] 를 구체
# pydantic 모델로 좁힌다. ptz/capabilities 도 마찬가지라 원본 dict 를 그대로 반환한다.


class PtzMoveRequest(BaseModel):
    pan: float = Field(ge=-1, le=1)
    tilt: float = Field(ge=-1, le=1)


class PtzZoomRequest(BaseModel):
    delta: float


class StreamState(BaseModel):
    status: Literal["idle", "streaming"]
    url: Optional[str] = None


class StreamSetRequest(BaseModel):
    streaming: bool


class SendTtsRequest(BaseModel):
    text: str
    speakerId: Optional[int] = None
    speed: Optional[float] = None


def _client() -> CoreApiClient:
    return CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)


def _raise_from_tool_error(exc: ToolError) -> None:
    raise InternalApiError(exc.code or "CORE_API_UNAVAILABLE", str(exc), detail=exc.detail) from exc


def _summary_from_wire(item: dict[str, Any]) -> DeviceSummary:
    return DeviceSummary.model_validate({**item, "id": hex_to_device_id(item["id"])})


def _detail_from_wire(item: dict[str, Any]) -> DeviceDetail:
    return DeviceDetail.model_validate({**item, "id": hex_to_device_id(item["id"])})


# ── mock 데이터 (WAVEHOME_CORE_API_MOCK=true) ───────────────────────────────
# app/tools/db_query.py 의 MOCK_DEVICES 를 확장해서, "장치 목록 조회 -> 이름으로 제어" 데모
# 흐름에서 id/이름이 어긋나지 않게 한다.

_MOCK_CAPABILITIES: dict[str, DeviceClassCapabilities] = {
    "tuya_ep2h": DeviceClassCapabilities(
        **{
            "class": "tuya_ep2h",
            "label": "스마트 플러그",
            "actions": [
                {"name": "on", "description": "전원 켜기", "attributes": ["Stateful"]},
                {"name": "off", "description": "전원 끄기", "attributes": ["Stateful"]},
                {"name": "toggle", "description": "전원 토글", "attributes": ["Toggle", "Stateful"]},
            ],
            "queries": [
                {"name": "power", "description": "순간 전력(W)"},
                {"name": "voltage", "description": "AC 전압(V)"},
                {"name": "status", "description": "전체 datapoint"},
            ],
            "triggerKinds": ["device_state"],
            "triggerableQueries": ["power", "voltage", "current"],
        }
    ),
    "philips_wiz_e29_color": DeviceClassCapabilities(
        **{
            "class": "philips_wiz_e29_color",
            "label": "WiZ 컬러 조명",
            "actions": [
                {"name": "on", "description": "전원 켜기", "attributes": ["Stateful"]},
                {"name": "off", "description": "전원 끄기", "attributes": ["Stateful"]},
                {"name": "toggle", "description": "전원 토글", "attributes": ["Toggle", "Stateful"]},
                {"name": "brightness", "description": "밝기 %", "attributes": ["Stateful"]},
                {"name": "color", "description": "RGB", "attributes": ["Stateful"]},
            ],
            "queries": [
                {"name": "state", "description": "{on, brightness}"},
                {"name": "brightness", "description": "{value, unit}"},
                {"name": "color", "description": "{r,g,b}"},
                {"name": "status", "description": "pilot 전체"},
            ],
            "triggerKinds": ["device_state"],
        }
    ),
    "reolink_e1_pro": DeviceClassCapabilities(
        **{
            "class": "reolink_e1_pro",
            "label": "실내 카메라 (Reolink E1 Pro)",
            "queries": [
                {"name": "stream", "description": "RTSP URI (main/sub, go2rtc)"},
                {"name": "status", "description": "{streaming, micLevel}"},
            ],
            "ptz": True,
        }
    ),
    "droid_cam": DeviceClassCapabilities(
        **{
            "class": "droid_cam",
            "label": "실내 카메라 (DroidCam)",
            "queries": [
                {"name": "capabilities", "description": "snapshot/stream/mic 플래그"},
                {"name": "session", "description": "HTTP 엔드포인트"},
                {"name": "status", "description": "연결·스트리밍 상태"},
                {"name": "stream", "description": "MJPEG source URI"},
            ],
            "ptz": False,
        }
    ),
}

_MOCK_STATE: dict[int, dict[str, Any]] = {
    MOCK_DEVICES[0]["id"]: {"switch": True, "voltage": 234.6, "current": 118.2, "power": 27.7, "energy": 12.4},
    MOCK_DEVICES[1]["id"]: {"on": True, "brightness": 70, "color": {"r": 255, "g": 196, "b": 120}},
}

# 카메라는 스위치/조명과 다른 축(스트리밍 on/off, pan/tilt 위치)이라 별도 mock 상태로 분리.
_MOCK_CAMERA_STATE: dict[int, dict[str, Any]] = {
    MOCK_DEVICES[2]["id"]: {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0},
    MOCK_DEVICES[3]["id"]: {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0},
}


def _mock_summary(device: dict[str, Any]) -> DeviceSummary:
    caps = _MOCK_CAPABILITIES.get(device["class"])
    return DeviceSummary(
        id=device["id"],
        name=device["name"],
        description=device.get("description", ""),
        **{"class": device["class"]},
        classLabel=caps.label if caps else device["class"],
        enabled=not bool(device.get("archived")),
        connected=True,
        stateSummary=_state_summary_text(device["id"]),
        room={"id": device["roomId"], "name": "거실"} if device.get("roomId") else None,
    )


def _state_summary_text(device_id: int) -> str:
    state = _MOCK_STATE.get(device_id, {})
    if "power" in state:
        return f"켜짐 · {state['power']}W" if state.get("switch") else "꺼짐"
    if "brightness" in state:
        return f"켜짐 · 밝기 {state['brightness']}%" if state.get("on") else "꺼짐"
    return "알 수 없음"


def _mock_device_by_id(device_id: int) -> Optional[dict[str, Any]]:
    return next((d for d in MOCK_DEVICES if d["id"] == device_id), None)


# ── REST 클라이언트 함수 ─────────────────────────────────────────────────


async def list_devices(
    *,
    user_id: Optional[int] = None,
    room_id: Optional[int] = None,
    device_class: Optional[str] = None,
    connected: Optional[bool] = None,
    enabled: Optional[bool] = None,
) -> list[DeviceSummary]:
    client = _client()
    if client.is_mock:
        items = MOCK_DEVICES
        if room_id is not None:
            items = [d for d in items if d["roomId"] == room_id]
        if device_class is not None:
            items = [d for d in items if d["class"] == device_class]
        return [_mock_summary(d) for d in items]

    params = {
        k: v
        for k, v in {
            "userId": user_id,
            "roomId": room_id,
            "class": device_class,
            "connected": connected,
            "enabled": enabled,
        }.items()
        if v is not None
    }
    try:
        response = await client.get("/devices", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [_summary_from_wire(item) for item in response.get("items", [])]


async def get_device(device_id: int) -> DeviceDetail:
    client = _client()
    if client.is_mock:
        device = _mock_device_by_id(device_id)
        if device is None:
            raise InternalApiError("NOT_FOUND", f"deviceId={device_id} 인 장치를 찾을 수 없습니다.")
        summary = _mock_summary(device)
        caps = _MOCK_CAPABILITIES.get(device["class"], DeviceClassCapabilities(**{"class": device["class"]}))
        return DeviceDetail(**summary.model_dump(by_alias=True), capabilities=caps)

    try:
        response = await client.get(f"/devices/{device_id_to_hex(device_id)}")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _detail_from_wire(response)


async def get_device_classes() -> list[DeviceClassCapabilities]:
    client = _client()
    if client.is_mock:
        return list(_MOCK_CAPABILITIES.values())

    try:
        response = await client.get("/device-classes")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [DeviceClassCapabilities.model_validate(item) for item in response.get("items", [])]


async def get_device_state(device_id: int) -> DeviceStateSnapshot:
    client = _client()
    if client.is_mock:
        device = _mock_device_by_id(device_id)
        if device is None:
            raise InternalApiError("NOT_FOUND", f"deviceId={device_id} 인 장치를 찾을 수 없습니다.")
        return DeviceStateSnapshot(deviceId=device_id, connected=True, state=_MOCK_STATE.get(device_id, {}))

    try:
        response = await client.get(f"/devices/{device_id_to_hex(device_id)}/state")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return DeviceStateSnapshot.model_validate({**response, "deviceId": hex_to_device_id(response["deviceId"])})


async def query_device(device_id: int, query_name: str, req: QueryDeviceRequest) -> QueryDeviceResponse:
    client = _client()
    if client.is_mock:
        device = _mock_device_by_id(device_id)
        if device is None:
            raise InternalApiError("NOT_FOUND", f"deviceId={device_id} 인 장치를 찾을 수 없습니다.")
        state = _MOCK_STATE.get(device_id, {})
        if query_name in ("status", "state"):
            result = dict(state)
        elif query_name in state:
            result = {query_name: state[query_name]}
        else:
            raise InternalApiError("QUERY_NOT_FOUND", f"'{query_name}' 은 해당 클래스에 없는 query 입니다.")
        return QueryDeviceResponse(deviceId=device_id, query=query_name, result=result)

    try:
        response = await client.post(
            f"/devices/{device_id_to_hex(device_id)}/query/{query_name}", json=req.model_dump()
        )
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return QueryDeviceResponse.model_validate({**response, "deviceId": hex_to_device_id(response["deviceId"])})


async def invoke_device_action(
    device_id: int, action_name: str, req: InvokeDeviceRequest
) -> InvokeDeviceResponse:
    client = _client()
    if client.is_mock:
        device = _mock_device_by_id(device_id)
        if device is None:
            raise InternalApiError("NOT_FOUND", f"deviceId={device_id} 인 장치를 찾을 수 없습니다.")
        state = _MOCK_STATE.setdefault(device_id, {})
        _apply_mock_action(state, action_name, req.params)
        return InvokeDeviceResponse(ok=True, deviceId=device_id, action=action_name, state=dict(state), eventId="evt_mock")

    try:
        response = await client.post(
            f"/devices/{device_id_to_hex(device_id)}/actions/{action_name}", json=req.model_dump(exclude_none=True)
        )
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return InvokeDeviceResponse.model_validate({**response, "deviceId": hex_to_device_id(response["deviceId"])})


def _apply_mock_action(state: dict[str, Any], action_name: str, params: dict[str, Any]) -> None:
    if action_name == "on":
        state["switch"] = True
        state["on"] = True
    elif action_name == "off":
        state["switch"] = False
        state["on"] = False
    elif action_name == "toggle":
        state["switch"] = not state.get("switch", False)
        state["on"] = state["switch"]
    elif action_name == "brightness" and "value" in params:
        state["brightness"] = params["value"]
    elif action_name == "color" and {"r", "g", "b"} <= params.keys():
        state["color"] = {"r": params["r"], "g": params["g"], "b": params["b"]}


async def get_ptz_capabilities(device_id: int) -> dict[str, Any]:
    """reolink_e1_pro 전용(device-tool-api.md:818). 응답 스키마 미문서화 — 원본 dict 반환."""
    client = _client()
    if client.is_mock:
        return {"pan": True, "tilt": True, "zoom": True}

    try:
        return await client.get(f"/devices/{device_id_to_hex(device_id)}/ptz/capabilities")
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def ptz_move(device_id: int, req: PtzMoveRequest) -> dict[str, Any]:
    client = _client()
    if client.is_mock:
        state = _MOCK_CAMERA_STATE.setdefault(device_id, {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0})
        state["pan"], state["tilt"] = req.pan, req.tilt
        return {"ok": True}

    try:
        return await client.post(f"/devices/{device_id_to_hex(device_id)}/ptz/move", json=req.model_dump())
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def ptz_stop(device_id: int) -> dict[str, Any]:
    client = _client()
    if client.is_mock:
        return {"ok": True}

    try:
        return await client.post(f"/devices/{device_id_to_hex(device_id)}/ptz/stop", json={})
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def ptz_zoom(device_id: int, req: PtzZoomRequest) -> dict[str, Any]:
    client = _client()
    if client.is_mock:
        state = _MOCK_CAMERA_STATE.setdefault(device_id, {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0})
        state["zoom"] = state.get("zoom", 0.0) + req.delta
        return {"ok": True}

    try:
        return await client.post(f"/devices/{device_id_to_hex(device_id)}/ptz/zoom", json=req.model_dump())
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def get_stream(device_id: int) -> StreamState:
    client = _client()
    if client.is_mock:
        state = _MOCK_CAMERA_STATE.setdefault(device_id, {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0})
        streaming = state["streaming"]
        url = get_settings().mock_camera_stream_url if streaming else None
        return StreamState(status="streaming" if streaming else "idle", url=url)

    try:
        response = await client.get(f"/devices/{device_id_to_hex(device_id)}/stream")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return StreamState.model_validate(response)


async def set_stream(device_id: int, req: StreamSetRequest) -> StreamState:
    client = _client()
    if client.is_mock:
        state = _MOCK_CAMERA_STATE.setdefault(device_id, {"streaming": False, "pan": 0.0, "tilt": 0.0, "zoom": 0.0})
        state["streaming"] = req.streaming
        url = get_settings().mock_camera_stream_url if req.streaming else None
        return StreamState(status="streaming" if req.streaming else "idle", url=url)

    try:
        response = await client.put(f"/devices/{device_id_to_hex(device_id)}/stream", json=req.model_dump())
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return StreamState.model_validate(response)


async def send_tts(device_id: int, req: SendTtsRequest) -> dict[str, Any]:
    """성공 응답 바디 미문서화(device-tool-api.md:833) — 원본 dict 반환.
    백엔드 TTS 엔진·스트림 경로 미구축 시 503 TTS_UNAVAILABLE(ToolError 로 전파)."""
    client = _client()
    if client.is_mock:
        return {"ok": True}

    try:
        return await client.post(f"/devices/{device_id_to_hex(device_id)}/tts", json=req.model_dump(exclude_none=True))
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def resolve_device_id(room_id: int, name: str, *, user_id: Optional[int] = None) -> int:
    """roomId 범위에서 장치 이름 부분일치(대소문자 무시)로 deviceId 해석.

    db_query.py 의 device 테이블 조회로 구현한다(device-tool-api.md §설계원칙 4).
    0건 -> NOT_FOUND, 2건 이상 -> AMBIGUOUS_DEVICE.
    """
    from app.tools.db_query import DbQuery, query_db

    filter_: dict[str, Any] = {"roomId": room_id, "archived": 0}
    if user_id is not None:
        filter_["userId"] = user_id
    [result] = await query_db([DbQuery(table="device", filter=filter_)])
    if result.error is not None:
        raise InternalApiError(result.error.code, result.error.message)

    needle = name.strip().lower()
    matches = [item for item in result.items if needle in str(item.get("name", "")).lower()]
    if not matches:
        raise InternalApiError(
            "NOT_FOUND", f"'{name}' 이름과 일치하는 장치를 roomId={room_id} 에서 찾을 수 없습니다."
        )
    if len(matches) > 1:
        raise InternalApiError(
            "AMBIGUOUS_DEVICE",
            f"'{name}' 이름에 매칭되는 장치가 {len(matches)}건입니다.",
            detail={"matches": [{"id": m["id"], "name": m["name"]} for m in matches]},
        )
    return int(matches[0]["id"])
