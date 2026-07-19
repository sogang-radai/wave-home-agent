"""device-tool-api.md 의 룰·예약(`/internal/v1/rules`) + IR 커맨드(`/internal/v1/ir-commands`)
+ 이벤트(`/internal/v1/events`) REST 클라이언트.

deviceId 는 이 모듈의 시그니처·타입에서는 항상 int(app/tools/device_id.py 로 hex 변환은
httpx 호출 경계에서만). trigger/action 내부까지 재귀적으로 변환한다.
"""

from typing import Any, Literal, Optional, Union
from uuid import uuid4
import logging

from pydantic import BaseModel, Field, ValidationError

from app.clients.core import CoreApiClient, ToolError
from app.config import get_settings
from app.tools.device_id import device_id_to_hex, hex_to_device_id
from app.tools.errors import InternalApiError
from app.tools.devices_internal import fetch_device_id_maps

logger = logging.getLogger(__name__)


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
# id_to_external/external_to_id 는 devices_internal.fetch_device_id_maps() 가 돌려주는 실제
# DB 조회 결과다. device_id_to_hex()/hex_to_device_id()(zero-pad 공식)는 여기서 쓰지 않는다 -
# real backend 의 externalId 는 그 공식으로 못 구하고(device_list.json 에 박힌 임의값),
# 공식으로 만든 값은 룰 생성은 성공해도 실행 시점에 조용히 실패한다(실측 확인). 매핑에
# 없는 경우에만(마이그레이션 전 레거시 데이터 등, 흔치 않음) 공식을 최후 수단으로 쓴다.


def _trigger_to_wire(trigger: Optional[RuleTrigger], id_to_external: dict[int, str]) -> Optional[dict[str, Any]]:
    if trigger is None:
        return None
    data = trigger.model_dump()
    data["deviceId"] = id_to_external.get(data["deviceId"], device_id_to_hex(data["deviceId"]))
    return data


def _action_to_wire(action: RuleAction, id_to_external: dict[int, str]) -> dict[str, Any]:
    data = action.model_dump()
    data["deviceId"] = id_to_external.get(data["deviceId"], device_id_to_hex(data["deviceId"]))
    return data


def _rule_to_wire(
    req: Union[CreateRuleRequest, UpdateRuleRequest], id_to_external: dict[int, str]
) -> dict[str, Any]:
    data = req.model_dump(exclude_none=True)
    if "trigger" in data and data["trigger"] is not None:
        data["trigger"]["deviceId"] = id_to_external.get(
            data["trigger"]["deviceId"], device_id_to_hex(data["trigger"]["deviceId"])
        )
    if "action" in data and data["action"] is not None:
        data["action"]["deviceId"] = id_to_external.get(
            data["action"]["deviceId"], device_id_to_hex(data["action"]["deviceId"])
        )
    return data


def _rule_from_wire(item: dict[str, Any], external_to_id: dict[str, int]) -> RuleView:
    item = dict(item)
    if item.get("trigger"):
        wire_id = item["trigger"]["deviceId"]
        item["trigger"] = {**item["trigger"], "deviceId": external_to_id.get(wire_id, hex_to_device_id(wire_id))}
    if item.get("action"):
        wire_id = item["action"]["deviceId"]
        item["action"] = {**item["action"], "deviceId": external_to_id.get(wire_id, hex_to_device_id(wire_id))}
    return RuleView.model_validate(item)


def _try_rule_from_wire(item: dict[str, Any], external_to_id: dict[str, int]) -> Optional[RuleView]:
    try:
        return _rule_from_wire(item, external_to_id)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        logger.warning("skipping invalid rule from core: id=%s error=%s", item.get("id"), exc)
        return None


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
        action=RuleAction(deviceId=10, name="off"),
        execMode="once",
        cooldownMs=0,
        actionDeviceName="침실 TV",
    ),
    # 아래 2개는 mock.db(db-schema.md 시딩 데이터)의 automation_rule 중 지금 스펙(cron 미지원,
    # ScheduleDaily/Weekly만)으로 변환 가능한 것만 옮겨온 것. mock.db의 나머지 2개
    # (외출 시 에어컨 자동정지 - presence 트리거, 인덕션 안전 타이머 - 트리거 발동 후 상대 지연)와
    # alarm의 sound 타입은 지금 RuleTrigger/AlarmMethod 스펙에 없는 개념이라 보류 중 — 팀 확인 필요.
    RuleView(
        id="rule_schedule_bedroom_light_off",
        name="취침 시간 자동 소등",
        enabled=True,
        trigger=None,
        schedule=ScheduleDaily(time="23:00"),  # mock.db: cron "0 23 * * *"
        action=RuleAction(deviceId=11, name="off"),
        execMode="once",
        cooldownMs=0,
        actionDeviceName="침실 조명",
    ),
    RuleView(
        id="rule_schedule_wake_light_ramp",
        name="기상 조명 서서히 밝히기",
        enabled=True,
        trigger=None,
        schedule=ScheduleWeekly(time="06:30", daysOfWeek=["mon", "tue", "wed", "thu", "fri"]),  # mock.db: cron "30 6 * * 1-5"
        # mock.db 원본 action은 name="ramp_on", params={"durationMs": 1800000}(30분에 걸쳐 서서히
        # 밝힘) — 조명 클래스에 없는 액션이라 이 필드는 못 옮긴다. 스케줄만 재현하고 즉시 on으로 대체.
        action=RuleAction(deviceId=11, name="on"),
        execMode="once",
        cooldownMs=0,
        actionDeviceName="침실 조명",
    ),
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
        deviceId=8,
        deviceName="플러그3 - 에어컨",
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

    id_to_external, external_to_id = await fetch_device_id_maps()
    params = {
        k: v
        for k, v in {
            "deviceId": id_to_external.get(device_id, device_id_to_hex(device_id)) if device_id is not None else None,
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
    return [
        rule
        for item in response.get("items", [])
        if (rule := _try_rule_from_wire(item, external_to_id)) is not None
    ]


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
    _, external_to_id = await fetch_device_id_maps()
    return _rule_from_wire(response, external_to_id)


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

    id_to_external, external_to_id = await fetch_device_id_maps()
    try:
        response = await client.post("/rules", json=_rule_to_wire(req, id_to_external))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response, external_to_id)


async def update_rule(rule_id: str, req: UpdateRuleRequest) -> RuleView:
    client = _client()
    if client.is_mock:
        for idx, rule in enumerate(_MOCK_RULES):
            if rule.id == rule_id:
                updated = rule.model_copy(update=req.model_dump(exclude_none=True))
                _MOCK_RULES[idx] = updated
                return updated
        raise InternalApiError("NOT_FOUND", f"ruleId={rule_id} 인 룰을 찾을 수 없습니다.")

    id_to_external, external_to_id = await fetch_device_id_maps()
    try:
        response = await client.put(f"/rules/{rule_id}", json=_rule_to_wire(req, id_to_external))
    except ToolError as exc:
        _raise_from_tool_error(exc)
    return _rule_from_wire(response, external_to_id)


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
    _, external_to_id = await fetch_device_id_maps()
    return _rule_from_wire(response, external_to_id)


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

    id_to_external, external_to_id = await fetch_device_id_maps()
    params: dict[str, Any] = {"limit": limit}
    if types:
        params["types"] = ",".join(types)
    if device_id is not None:
        params["deviceId"] = id_to_external.get(device_id, device_id_to_hex(device_id))
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
            {
                **item,
                "deviceId": (
                    external_to_id.get(item["deviceId"], hex_to_device_id(item["deviceId"]))
                    if item.get("deviceId")
                    else None
                ),
            }
        )
        for item in items
    ]
