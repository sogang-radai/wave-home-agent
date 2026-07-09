"""device-tool-api.md 의 룰·예약(`/internal/v1/rules`) + IR 커맨드(`/internal/v1/ir-commands`)
+ 이벤트(`/internal/v1/events`) REST 클라이언트.

deviceId 는 이 모듈의 시그니처·타입에서는 항상 int(app/tools/device_id.py 로 hex 변환은
httpx 호출 경계에서만). trigger/action 내부까지 재귀적으로 변환한다.
"""

from typing import Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from app.clients.core import CoreApiClient, ToolError
from app.config import get_settings
from app.tools.device_id import device_id_to_hex, hex_to_device_id
from app.tools.errors import InternalApiError


# ── 타입 (device-tool-api.md §타입) ─────────────────────────────────────────

DayOfWeek = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ExecMode = Literal["once", "repeat", "toggle"]


class GestureTrigger(BaseModel):
    kind: Literal["gesture"] = "gesture"
    deviceId: int
    gestureSetPath: str
    classId: int


class DeviceStateTrigger(BaseModel):
    kind: Literal["device_state"] = "device_state"
    deviceId: int
    query: str
    op: Literal[">", ">=", "<", "<=", "=="]
    value: float


class IrRecvTrigger(BaseModel):
    kind: Literal["ir_recv"] = "ir_recv"
    deviceId: int
    commandId: str


RuleTrigger = Union[GestureTrigger, DeviceStateTrigger, IrRecvTrigger]


class ScheduleOnce(BaseModel):
    repeat: Literal["once"] = "once"
    delayMinutes: int


class ScheduleDaily(BaseModel):
    repeat: Literal["daily"] = "daily"
    time: str


class ScheduleWeekly(BaseModel):
    repeat: Literal["weekly"] = "weekly"
    time: str
    daysOfWeek: list[DayOfWeek]


RuleSchedule = Union[ScheduleOnce, ScheduleDaily, ScheduleWeekly]


class RuleAction(BaseModel):
    deviceId: int
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class Rule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    trigger: Optional[RuleTrigger] = None
    schedule: Optional[RuleSchedule] = None
    action: RuleAction
    execMode: ExecMode = "once"
    repeatIntervalMs: Optional[int] = None
    cooldownMs: int = 0


class RuleView(Rule):
    actionDeviceName: str = ""
    triggerDeviceName: Optional[str] = None


class CreateRuleRequest(BaseModel):
    name: str
    enabled: bool = True
    trigger: Optional[RuleTrigger] = None
    schedule: Optional[RuleSchedule] = None
    action: RuleAction
    execMode: ExecMode = "once"
    repeatIntervalMs: Optional[int] = None
    cooldownMs: int = 0


class UpdateRuleRequest(BaseModel):
    """Partial<CreateRuleRequest> — 백엔드 스펙은 PUT 이지만 실제로는 부분 갱신
    시맨틱이므로 exclude_none=True 로 세팅된 필드만 전송한다."""

    name: Optional[str] = None
    enabled: Optional[bool] = None
    trigger: Optional[RuleTrigger] = None
    schedule: Optional[RuleSchedule] = None
    action: Optional[RuleAction] = None
    execMode: Optional[ExecMode] = None
    repeatIntervalMs: Optional[int] = None
    cooldownMs: Optional[int] = None


class IrCommandSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    deviceHint: Optional[str] = None
    unit: Literal["us"] = "us"
    source: Literal["learned", "manual"]
    createdAt: str


class IrCommand(IrCommandSummary):
    timings: list[int] = Field(default_factory=list)


class DeviceEvent(BaseModel):
    id: str
    type: Literal["connection", "gesture", "ir", "execution", "schedule"]
    occurredAt: str
    deviceId: Optional[int] = None
    deviceName: Optional[str] = None
    message: str = ""
    triggeredBy: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


def _client() -> CoreApiClient:
    return CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)


def _raise_from_tool_error(exc: ToolError) -> None:
    raise InternalApiError(exc.code or "CORE_API_UNAVAILABLE", str(exc), detail=exc.detail) from exc


# ── hex<->int 재귀 변환 헬퍼 (trigger/action 내부까지) ───────────────────────


def _trigger_to_wire(trigger: Optional[RuleTrigger]) -> Optional[dict[str, Any]]:
    if trigger is None:
        return None
    data = trigger.model_dump()
    data["deviceId"] = device_id_to_hex(data["deviceId"])
    return data


def _action_to_wire(action: RuleAction) -> dict[str, Any]:
    data = action.model_dump()
    data["deviceId"] = device_id_to_hex(data["deviceId"])
    return data


def _rule_to_wire(req: Union[CreateRuleRequest, UpdateRuleRequest]) -> dict[str, Any]:
    data = req.model_dump(exclude_none=True)
    if "trigger" in data and data["trigger"] is not None:
        data["trigger"]["deviceId"] = device_id_to_hex(data["trigger"]["deviceId"])
    if "action" in data and data["action"] is not None:
        data["action"]["deviceId"] = device_id_to_hex(data["action"]["deviceId"])
    return data


def _rule_from_wire(item: dict[str, Any]) -> RuleView:
    item = dict(item)
    if item.get("trigger"):
        item["trigger"] = {**item["trigger"], "deviceId": hex_to_device_id(item["trigger"]["deviceId"])}
    if item.get("action"):
        item["action"] = {**item["action"], "deviceId": hex_to_device_id(item["action"]["deviceId"])}
    return RuleView.model_validate(item)


# ── mock 상태 (WAVEHOME_CORE_API_MOCK=true) ─────────────────────────────────
# job_store 와 마찬가지로 프로세스 재시작 시 소실되는 인메모리 CRUD — 생성한 룰이 이후
# GET/DELETE 에 보여야 자연스러운 데모가 되므로 상태를 갖는 목업이 필요하다.

_MOCK_RULES: list[RuleView] = [
    RuleView(
        id="rule_schedule_tv_off_once",
        name="30분 뒤 TV 끄기",
        enabled=True,
        trigger=None,
        schedule=ScheduleOnce(delayMinutes=30),
        action=RuleAction(deviceId=7714208883279181, name="off"),
        execMode="once",
        cooldownMs=0,
        actionDeviceName="거실 에어컨",
    )
]

_MOCK_IR_COMMANDS: list[IrCommand] = [
    IrCommand(
        id="ir_ac_power",
        name="에어컨 전원",
        description="LG 에어컨 전원 토글 (학습됨)",
        deviceHint="LG 에어컨",
        source="learned",
        createdAt="2026-07-01 10:00:00",
        timings=[9000, 4500, 560, 560, 560, 1690, 560, 39000],
    )
]

_MOCK_EVENTS: list[DeviceEvent] = [
    DeviceEvent(
        id="evt_mock_1",
        type="execution",
        occurredAt="2026-07-06 10:05:12",
        deviceId=7714208883279181,
        deviceName="거실 에어컨",
        message="on 실행",
        triggeredBy="agent:manual",
    )
]


# ── 룰 CRUD ─────────────────────────────────────────────────────────────────


async def list_rules(
    *,
    device_id: Optional[int] = None,
    enabled: Optional[bool] = None,
    has_schedule: Optional[bool] = None,
    has_trigger: Optional[bool] = None,
) -> list[RuleView]:
    client = _client()
    if client.is_mock:
        items = _MOCK_RULES
        if device_id is not None:
            items = [r for r in items if r.action.deviceId == device_id]
        if enabled is not None:
            items = [r for r in items if r.enabled == enabled]
        if has_schedule is not None:
            items = [r for r in items if (r.schedule is not None) == has_schedule]
        if has_trigger is not None:
            items = [r for r in items if (r.trigger is not None) == has_trigger]
        return items

    params = {
        k: v
        for k, v in {
            "deviceId": device_id_to_hex(device_id) if device_id is not None else None,
            "enabled": enabled,
            "hasSchedule": has_schedule,
            "hasTrigger": has_trigger,
        }.items()
        if v is not None
    }
    try:
        response = await client.get("/rules", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [_rule_from_wire(item) for item in response.get("items", [])]


async def get_rule(rule_id: str) -> RuleView:
    client = _client()
    if client.is_mock:
        rule = next((r for r in _MOCK_RULES if r.id == rule_id), None)
        if rule is None:
            raise InternalApiError("NOT_FOUND", f"ruleId={rule_id} 인 룰을 찾을 수 없습니다.")
        return rule

    try:
        response = await client.get(f"/rules/{rule_id}")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response)


async def create_rule(req: CreateRuleRequest) -> RuleView:
    client = _client()
    if client.is_mock:
        rule = RuleView(
            id=f"rule_agent_{uuid4().hex[:12]}",
            actionDeviceName=_mock_device_name(req.action.deviceId),
            **req.model_dump(),
        )
        _MOCK_RULES.append(rule)
        return rule

    try:
        response = await client.post("/rules", json=_rule_to_wire(req))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response)


async def update_rule(rule_id: str, req: UpdateRuleRequest) -> RuleView:
    client = _client()
    if client.is_mock:
        for idx, rule in enumerate(_MOCK_RULES):
            if rule.id == rule_id:
                updated = rule.model_copy(update=req.model_dump(exclude_none=True))
                _MOCK_RULES[idx] = updated
                return updated
        raise InternalApiError("NOT_FOUND", f"ruleId={rule_id} 인 룰을 찾을 수 없습니다.")

    try:
        response = await client.put(f"/rules/{rule_id}", json=_rule_to_wire(req))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response)


async def delete_rule(rule_id: str) -> None:
    client = _client()
    if client.is_mock:
        before = len(_MOCK_RULES)
        _MOCK_RULES[:] = [r for r in _MOCK_RULES if r.id != rule_id]
        if len(_MOCK_RULES) == before:
            raise InternalApiError("NOT_FOUND", f"ruleId={rule_id} 인 룰을 찾을 수 없습니다.")
        return

    try:
        await client.delete(f"/rules/{rule_id}")
    except ToolError as exc:
        _raise_from_tool_error(exc)


async def set_rule_enabled(rule_id: str, enabled: bool) -> RuleView:
    client = _client()
    if client.is_mock:
        return await update_rule(rule_id, UpdateRuleRequest(enabled=enabled))

    try:
        response = await client.put(f"/rules/{rule_id}/enabled", json={"enabled": enabled})
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response)


async def execute_rule(rule_id: str) -> dict[str, Any]:
    client = _client()
    if client.is_mock:
        rule = next((r for r in _MOCK_RULES if r.id == rule_id), None)
        if rule is None:
            raise InternalApiError("NOT_FOUND", f"ruleId={rule_id} 인 룰을 찾을 수 없습니다.")
        if not rule.enabled:
            raise InternalApiError("RULE_DISABLED", f"ruleId={rule_id} 는 비활성 상태입니다.")
        return {"ok": True, "ruleId": rule_id}

    try:
        return await client.post(f"/rules/{rule_id}/execute")
    except ToolError as exc:
        _raise_from_tool_error(exc)


def _mock_device_name(device_id: int) -> str:
    from app.tools.db_query import MOCK_DEVICES

    device = next((d for d in MOCK_DEVICES if d["id"] == device_id), None)
    return device["name"] if device else str(device_id)


# ── IR 커맨드 (조회 전역, 송신은 devices_internal.invoke_device_action 의 send_ir action) ──


async def list_ir_commands(
    *, device_hint: Optional[str] = None, source: Optional[Literal["learned", "manual"]] = None
) -> list[IrCommandSummary]:
    client = _client()
    if client.is_mock:
        items = _MOCK_IR_COMMANDS
        if device_hint is not None:
            items = [c for c in items if c.deviceHint == device_hint]
        if source is not None:
            items = [c for c in items if c.source == source]
        return [IrCommandSummary.model_validate(c.model_dump()) for c in items]

    params = {k: v for k, v in {"deviceHint": device_hint, "source": source}.items() if v is not None}
    try:
        response = await client.get("/ir-commands", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return [IrCommandSummary.model_validate(item) for item in response.get("items", [])]


async def get_ir_command(command_id: str) -> IrCommand:
    client = _client()
    if client.is_mock:
        command = next((c for c in _MOCK_IR_COMMANDS if c.id == command_id), None)
        if command is None:
            raise InternalApiError("NOT_FOUND", f"commandId={command_id} 인 IR 커맨드를 찾을 수 없습니다.")
        return command

    try:
        response = await client.get(f"/ir-commands/{command_id}")
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return IrCommand.model_validate(response)


# ── 이벤트 ────────────────────────────────────────────────────────────────


async def list_events(
    *,
    types: Optional[list[str]] = None,
    device_id: Optional[int] = None,
    from_: Optional[str] = None,
    to: Optional[str] = None,
    limit: int = 50,
) -> list[DeviceEvent]:
    client = _client()
    limit = max(1, min(limit, 200))
    if client.is_mock:
        items = _MOCK_EVENTS
        if device_id is not None:
            items = [e for e in items if e.deviceId == device_id]
        return items[:limit]

    params: dict[str, Any] = {"limit": limit}
    if types:
        params["types"] = ",".join(types)
    if device_id is not None:
        params["deviceId"] = device_id_to_hex(device_id)
    if from_ is not None:
        params["from"] = from_
    if to is not None:
        params["to"] = to
    try:
        response = await client.get("/events", params)
    except ToolError as exc:
        _raise_from_tool_error(exc)
    items = response.get("items", [])
    return [
        DeviceEvent.model_validate(
            {**item, "deviceId": hex_to_device_id(item["deviceId"]) if item.get("deviceId") else None}
        )
        for item in items
    ]
