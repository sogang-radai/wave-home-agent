"""LangChain @tool wrappers around app/tools/*.py mock functions.

Tools are built fresh per chat turn via build_tools(user_id), closing over the
authenticated userId from the request body. Device/schedule tools never let
the model supply userId (api.md frames it as authorization, not a filter).
query_db is the one exception: filter.userId is legitimate row-filter data the
model must supply, so make_query_db_tool injects/overwrites it server-side
instead of trusting whatever the model passes, to block a prompt-injected
cross-user data request.
"""

import json
from datetime import date
from typing import Any, Literal, Optional

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field, field_validator

from app.tools.db_query import TABLE_SPECS, DbQuery, DbQueryError, DbQueryResultItem, MAX_QUERIES, query_db
from app.tools import alarms_internal, devices_internal, rules_internal, schedule_tasks_internal
from app.tools.alarms_internal import CreateAlarmRequest
from app.tools.devices_internal import (
    ExecMode,
    InvokeDeviceRequest,
    PtzMoveRequest,
    PtzZoomRequest,
    QueryDeviceRequest,
    SendTtsRequest,
    StreamSetRequest,
)
from app.tools.rag_search import RagTarget, rag_search
from app.tools.rules_internal import (
    CreateRuleRequest,
    DeviceStateTrigger,
    GestureTrigger,
    IrRecvTrigger,
    RuleAction,
    RuleSchedule,
)
from app.tools.schedule_tasks_internal import CreateScheduleTaskRequest, DayOfWeek, ScheduleCategory


class _QueryDbArgs(BaseModel):
    queries: list[DbQuery] = Field(..., description="최대 10개의 배치 조회. api.md §2.1 참고.")


_QUERY_DB_USAGE = """정확한 최신 값이 필요할 때 사용하세요: 특정 날짜의 수면 세션/통계, 오늘 일정, 정확한 점수/시간 등
구조화된 raw row를 조회합니다. "어젯밤", "오늘", "정확히 몇 점" 같은 질문에 적합합니다."""


def _describe_table(table: str) -> str:
    """Renders one TABLE_SPECS entry (app/tools/db_query.py) as a line for the
    query_db tool description, so the model sees the real per-table filter
    rules up front instead of learning them from an INVALID_FILTER error on
    its first guess."""
    spec = TABLE_SPECS.get(table)
    if spec is None:
        return f"- {table}"
    optional = sorted(spec.allowed - spec.required_any)
    bits = []
    if spec.required_any:
        bits.append(f"{'|'.join(sorted(spec.required_any))} 중 최소 1개 필수")
    if optional:
        bits.append(f"선택 필터: {', '.join(optional)}")
    line = f"- {table}: " + (" / ".join(bits) if bits else "필터 없음")
    if "userId" in spec.allowed:
        line += " (userId는 서버가 현재 사용자로 자동 주입)"
    if table == "power_report":
        line += " | period는 1h|24h|1w|1mo만 (month/day 금지). 하루 총량=period:24h+periodStart:YYYY-MM-DD"
    if table == "sleep_report":
        line += " | period는 daily|weekly"
    return line


def _describe_tables(tables: set[str]) -> str:
    return "\n".join(_describe_table(t) for t in sorted(tables) if t in TABLE_SPECS)


def make_query_db_tool(user_id: int, *, allowed_tables: Optional[set[str]] = None) -> BaseTool:
    """allowed_tables restricts which `table` values a domain subgraph may query
    (app/graph/domain_tools.py). Disallowed tables come back as a per-query
    INVALID_FILTER error, same shape as db_query.py's own table validation,
    instead of silently dropping or reaching the real backend.

    The tool description is generated from TABLE_SPECS (app/tools/db_query.py)
    - the actual validation rules - rather than hand-written prose, so it
    can't drift out of sync with them, and each domain only sees the rules
    for tables it's actually allowed to query."""
    tables = allowed_tables if allowed_tables is not None else set(TABLE_SPECS)
    description = f"{_QUERY_DB_USAGE}\n\n테이블별 filter 규칙:\n{_describe_tables(tables)}"

    async def _query_db(queries: list[DbQuery]) -> str:
        for q in queries:
            spec = TABLE_SPECS.get(q.table)
            # Tables that accept userId always get the authenticated user injected,
            # even when the model omits the key (otherwise required_any fails as 0건).
            if spec is not None and "userId" in spec.allowed:
                q.filter["userId"] = user_id

        results: list[DbQueryResultItem] = []
        for q in queries[:MAX_QUERIES]:
            if allowed_tables is not None and q.table not in allowed_tables:
                results.append(
                    DbQueryResultItem(
                        table=q.table,
                        count=0,
                        items=[],
                        error=DbQueryError(
                            code="INVALID_FILTER",
                            message=f"이 도메인에서는 조회할 수 없는 테이블입니다: {q.table}",
                            field="table",
                        ),
                    )
                )
                continue
            results.extend(await query_db([q]))
        return _to_json([r.model_dump() for r in results])

    return tool("query_db", _query_db, description=description, args_schema=_QueryDbArgs)


class _RagSearchArgs(BaseModel):
    query: str = Field(..., description="검색할 자연어 질의")
    targets: list[RagTarget] = Field(..., description="검색 대상 컬렉션 목록. api.md §2.6 참고.")


def make_rag_search_tool(*, allowed_collections: Optional[set[str]] = None) -> BaseTool:
    """allowed_collections restricts which rag_search collections a domain
    subgraph may target (app/graph/domain_tools.py); other targets are dropped
    before the call."""

    @tool("rag_search", args_schema=_RagSearchArgs)
    async def _rag_search(query: str, targets: list[RagTarget]) -> str:
        """과거에 만들어진 자연어 요약(리포트 문장, 기간별 패턴 설명)을 의미 기반으로 검색합니다.
        "요즘", "최근", "패턴", "이전보다", "왜 그런지" 같은 장기 맥락·비교·원인 질문에 적합합니다.
        정확한 최신 수치가 필요하면 query_db를 대신 쓰세요."""
        if allowed_collections is not None:
            targets = [t for t in targets if t.collection in allowed_collections]
        if not targets:
            return _to_json([])
        results = await rag_search(query, targets)
        return _to_json([r.model_dump() for r in results])

    return _rag_search


class _ListDevicesArgs(BaseModel):
    room_id: Optional[int] = Field(
        None, description="조회할 방 ID. 모르면 생략하거나 0(전체 방)"
    )


def make_list_devices_tool(user_id: int) -> BaseTool:
    @tool("list_devices", args_schema=_ListDevicesArgs)
    async def _list_devices(room_id: Optional[int] = None) -> str:
        """방에 속한 가전 기기 요약(연결 상태 포함)을 조회합니다. 세부 action/query 는
        get_device_capabilities 로 확인하세요. room_id를 모르면 생략하거나 0으로 두면
        사용자 범위 전체를 조회합니다."""
        scoped_room = room_id if room_id and room_id > 0 else None
        devices = await devices_internal.list_devices(user_id=user_id, room_id=scoped_room)
        return _to_json([d.model_dump(by_alias=True) for d in devices])

    return _list_devices


class _GetDeviceCapabilitiesArgs(BaseModel):
    room_id: int = Field(0, description="장치가 속한 방 ID. 모르면 0(전체 방 검색)")
    device: str = Field(..., description="장치 이름(부분 일치, 예: '거실 조명')")


def make_get_device_capabilities_tool(user_id: int) -> BaseTool:
    @tool("get_device_capabilities", args_schema=_GetDeviceCapabilitiesArgs)
    async def _get_device_capabilities(room_id: int = 0, device: str = "") -> str:
        """장치 이름으로 실행 가능한 action/query 목록(paramsSchema 포함)을 조회합니다.
        control_device/query_device 호출 전에 사용 가능한 이름을 확인할 때 씁니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        detail = await devices_internal.get_device(device_id)
        return _to_json(detail.model_dump(by_alias=True))

    return _get_device_capabilities


class _ControlDeviceArgs(BaseModel):
    room_id: int = Field(0, description="장치가 속한 방 ID. 모르면 0(전체 방 검색)")
    device: str = Field(..., description="장치 이름(부분 일치, 예: '거실 조명')")
    action: str = Field(
        ...,
        description="실행할 action 이름. get_device_capabilities 결과만 사용 (전원은 on|off|toggle)",
    )
    params: dict[str, Any] = Field(default_factory=dict, description="action params")
    exec_mode: ExecMode = Field("once", description="once|repeat|toggle")


def make_control_device_tool(user_id: int) -> BaseTool:
    @tool("control_device", args_schema=_ControlDeviceArgs)
    async def _control_device(
        room_id: int = 0,
        device: str = "",
        action: str = "",
        params: Optional[dict[str, Any]] = None,
        exec_mode: ExecMode = "once",
    ) -> str:
        """장치의 action을 즉시 실행합니다. action 이름은 반드시 get_device_capabilities 에
        나온 것만 쓰세요(플러그/조명/TV 전원은 'on'|'off'|'toggle'). turn_off/power_off/
        switch/끄기 같은 이름은 쓰지 마세요.
        컬러 조명 color 예: action='color', params={'r':255,'g':64,'b':0}
        밝기 예: action='brightness', params={'value':40}
        색온도 예: action='temperature', params={'value':2700}
        TV 볼륨/채널/D-pad 등 Repeat action은 params.count(1~32)로 반복 횟수를 지정합니다.
        예: 볼륨 10칸 → action='volume_up', params={'count': 10}, exec_mode='once'."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.invoke_device_action(
            device_id,
            action,
            InvokeDeviceRequest(params=params or {}, execMode=exec_mode, triggeredBy=f"agent:chat:{user_id}"),
        )
        return _to_json(result.model_dump())

    return _control_device


class _QueryDeviceArgs(BaseModel):
    room_id: int = Field(0, description="장치가 속한 방 ID. 모르면 0(전체 방 검색)")
    device: str = Field(..., description="장치 이름(부분 일치)")
    query: str = Field(..., description="조회할 query 이름 (get_device_capabilities 결과 참고)")
    params: dict[str, Any] = Field(default_factory=dict)


def make_query_device_tool(user_id: int) -> BaseTool:
    @tool("query_device", args_schema=_QueryDeviceArgs)
    async def _query_device(
        room_id: int = 0, device: str = "", query: str = "", params: Optional[dict[str, Any]] = None
    ) -> str:
        """장치의 실시간 센서·상태 값 하나를 조회합니다.
        query 는 get_device_capabilities 의 queries 이름만 쓰세요(예: power, switch, status, brightness).
        off/on/turn_off 같은 action 이름을 query 에 넣지 마세요."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.query_device(device_id, query, QueryDeviceRequest(params=params or {}))
        return _to_json(result.model_dump())

    return _query_device


class _GetDeviceStateArgs(BaseModel):
    room_id: int = Field(0, description="장치가 속한 방 ID. 모르면 0(전체 방 검색)")
    device: str = Field(..., description="장치 이름(부분 일치)")


def make_get_device_state_tool(user_id: int) -> BaseTool:
    @tool("get_device_state", args_schema=_GetDeviceStateArgs)
    async def _get_device_state(room_id: int = 0, device: str = "") -> str:
        """장치의 전체 런타임 상태 스냅샷을 조회합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        state = await devices_internal.get_device_state(device_id)
        return _to_json(state.model_dump())

    return _get_device_state


class _CameraDeviceArgs(BaseModel):
    room_id: int = Field(..., description="카메라가 속한 방 ID")
    device: str = Field(..., description="카메라 이름(부분 일치, 예: '현관 카메라')")


def make_get_ptz_capabilities_tool(user_id: int) -> BaseTool:
    @tool("get_ptz_capabilities", args_schema=_CameraDeviceArgs)
    async def _get_ptz_capabilities(room_id: int, device: str) -> str:
        """카메라의 PTZ(팬/틸트/줌) 지원 여부를 조회합니다. droid_cam 은 PTZ 를 지원하지 않습니다 -
        먼저 get_device_capabilities 로 class 를 확인하거나, 이 tool 이 실패하면 PTZ 미지원 카메라입니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        caps = await devices_internal.get_ptz_capabilities(device_id)
        return _to_json(caps)

    return _get_ptz_capabilities


class _PtzMoveArgs(_CameraDeviceArgs):
    pan: float = Field(..., ge=-1, le=1, description="좌우 이동. -1=완전 좌측, 1=완전 우측")
    tilt: float = Field(..., ge=-1, le=1, description="상하 이동. -1=완전 아래, 1=완전 위")


def make_ptz_move_tool(user_id: int) -> BaseTool:
    @tool("ptz_move", args_schema=_PtzMoveArgs)
    async def _ptz_move(room_id: int, device: str, pan: float, tilt: float) -> str:
        """카메라를 지정한 방향으로 회전시킵니다(reolink_e1_pro 전용)."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.ptz_move(device_id, PtzMoveRequest(pan=pan, tilt=tilt))
        return _to_json(result)

    return _ptz_move


def make_ptz_stop_tool(user_id: int) -> BaseTool:
    @tool("ptz_stop", args_schema=_CameraDeviceArgs)
    async def _ptz_stop(room_id: int, device: str) -> str:
        """진행 중인 카메라 회전을 멈춥니다(reolink_e1_pro 전용)."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.ptz_stop(device_id)
        return _to_json(result)

    return _ptz_stop


class _PtzZoomArgs(_CameraDeviceArgs):
    delta: float = Field(..., description="줌 변화량. 양수=확대, 음수=축소")


def make_ptz_zoom_tool(user_id: int) -> BaseTool:
    @tool("ptz_zoom", args_schema=_PtzZoomArgs)
    async def _ptz_zoom(room_id: int, device: str, delta: float) -> str:
        """카메라를 확대/축소합니다(reolink_e1_pro 전용)."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.ptz_zoom(device_id, PtzZoomRequest(delta=delta))
        return _to_json(result)

    return _ptz_zoom


def make_get_camera_stream_tool(user_id: int) -> BaseTool:
    @tool("get_camera_stream", args_schema=_CameraDeviceArgs)
    async def _get_camera_stream(room_id: int, device: str) -> str:
        """카메라 실시간 스트림의 현재 상태(재생 중 여부)와 재생 URL 을 조회합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        state = await devices_internal.get_stream(device_id)
        return _to_json(state.model_dump())

    return _get_camera_stream


class _SetCameraStreamArgs(_CameraDeviceArgs):
    streaming: bool = Field(..., description="true=스트림 시작, false=스트림 중지")


def make_set_camera_stream_tool(user_id: int) -> BaseTool:
    @tool("set_camera_stream", args_schema=_SetCameraStreamArgs)
    async def _set_camera_stream(room_id: int, device: str, streaming: bool) -> str:
        """카메라 실시간 스트림을 시작하거나 중지합니다. 시작 시 반환되는 url 을 사용자에게
        안내하세요(프론트가 그 url 로 영상을 재생합니다)."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        state = await devices_internal.set_stream(device_id, StreamSetRequest(streaming=streaming))
        return _to_json(state.model_dump())

    return _set_camera_stream


class _SendCameraTtsArgs(_CameraDeviceArgs):
    text: str = Field(..., description="카메라 스피커로 재생할 안내 문구")
    speed: Optional[float] = Field(None, description="재생 속도 배율. 생략 시 기본값")


def make_send_camera_tts_tool(user_id: int) -> BaseTool:
    @tool("send_camera_tts", args_schema=_SendCameraTtsArgs)
    async def _send_camera_tts(room_id: int, device: str, text: str, speed: Optional[float] = None) -> str:
        """카메라의 스피커로 텍스트를 음성 안내 방송합니다(양방향 오디오). 백엔드 TTS 엔진이
        준비되지 않았으면 실패할 수 있습니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        result = await devices_internal.send_tts(device_id, SendTtsRequest(text=text, speed=speed))
        return _to_json(result)

    return _send_camera_tts


class _ScheduleDeviceActionArgs(BaseModel):
    room_id: int = Field(..., description="장치가 속한 방 ID")
    device: str = Field(..., description="장치 이름(부분 일치)")
    action: str = Field(..., description="지연/반복 시 실행할 action 이름")
    schedule: RuleSchedule = Field(..., description='예: {"repeat":"once","delayMinutes":30}')
    params: dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = Field(None, description="예약 이름(생략 시 자동 생성)")


def make_schedule_device_action_tool(user_id: int) -> BaseTool:
    @tool("schedule_device_action", args_schema=_ScheduleDeviceActionArgs)
    async def _schedule_device_action(
        room_id: int,
        device: str,
        action: str,
        schedule: RuleSchedule,
        params: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> str:
        """장치 동작을 지연 또는 반복 실행되도록 예약합니다."""
        device_id = await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
        req = CreateRuleRequest(
            name=name or f"{device} {action} 예약",
            action=RuleAction(deviceId=device_id, name=action, params=params or {}),
            schedule=schedule,
        )
        rule = await rules_internal.create_rule(req)
        return _to_json(rule.model_dump())

    return _schedule_device_action


class _AutomateDeviceActionArgs(BaseModel):
    trigger_room_id: int = Field(..., description="트리거가 되는 장치가 속한 방 ID")
    trigger_device: str = Field(
        ..., description="트리거가 되는 장치 이름(부분 일치). 제스처=레이더(srs_r4sn), 기기상태=센서/플러그/조명, "
        "IR수신=Wave Station. get_device_capabilities의 triggerKinds로 지원 여부를 먼저 확인하세요."
    )
    trigger_kind: Literal["gesture", "device_state", "ir_recv"] = Field(..., description="트리거 종류")
    gesture_set_path: Optional[str] = Field(
        None, description="trigger_kind='gesture'일 때 필수. 제스처셋 경로(레이더 장치의 gestureSetPath)"
    )
    class_id: Optional[int] = Field(None, description="trigger_kind='gesture'일 때 필수. 감지할 제스처 클래스 ID")
    query: Optional[str] = Field(
        None, description="trigger_kind='device_state'일 때 필수. 감시할 query 이름(예: power). "
        "get_device_capabilities의 triggerableQueries 참고"
    )
    op: Optional[Literal[">", ">=", "<", "<=", "=="]] = Field(
        None, description="trigger_kind='device_state'일 때 필수. 비교 연산자"
    )
    value: Optional[float] = Field(None, description="trigger_kind='device_state'일 때 필수. 비교 임계값")
    command_id: Optional[str] = Field(
        None, description="trigger_kind='ir_recv'일 때 필수. list_ir_commands 결과의 id"
    )
    action_room_id: int = Field(..., description="트리거 발동 시 실행할 장치가 속한 방 ID")
    action_device: str = Field(..., description="트리거 발동 시 실행할 장치 이름(부분 일치)")
    action_name: str = Field(..., description="실행할 action 이름(get_device_capabilities 결과 참고)")
    params: dict[str, Any] = Field(default_factory=dict, description="action params")
    name: Optional[str] = Field(None, description="자동화 이름(생략 시 자동 생성)")


def make_automate_device_action_tool(user_id: int) -> BaseTool:
    @tool("automate_device_action", args_schema=_AutomateDeviceActionArgs)
    async def _automate_device_action(
        trigger_room_id: int,
        trigger_device: str,
        trigger_kind: Literal["gesture", "device_state", "ir_recv"],
        action_room_id: int,
        action_device: str,
        action_name: str,
        gesture_set_path: Optional[str] = None,
        class_id: Optional[int] = None,
        query: Optional[str] = None,
        op: Optional[Literal[">", ">=", "<", "<=", "=="]] = None,
        value: Optional[float] = None,
        command_id: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> str:
        """제스처 감지·기기 상태 임계값·IR 수신 같은 이벤트가 발생하면 다른 장치 동작을 실행하도록
        자동화를 등록합니다. 시간 기반 예약(지연/반복)은 schedule_device_action을 대신 쓰세요."""
        trigger_device_id = await devices_internal.resolve_device_id(trigger_room_id, trigger_device, user_id=user_id)

        if trigger_kind == "gesture":
            if gesture_set_path is None or class_id is None:
                raise ValueError("trigger_kind='gesture'에는 gesture_set_path와 class_id가 모두 필요합니다.")
            trigger = GestureTrigger(deviceId=trigger_device_id, gestureSetPath=gesture_set_path, classId=class_id)
        elif trigger_kind == "device_state":
            if query is None or op is None or value is None:
                raise ValueError("trigger_kind='device_state'에는 query, op, value가 모두 필요합니다.")
            trigger = DeviceStateTrigger(deviceId=trigger_device_id, query=query, op=op, value=value)
        else:
            if command_id is None:
                raise ValueError("trigger_kind='ir_recv'에는 command_id가 필요합니다.")
            trigger = IrRecvTrigger(deviceId=trigger_device_id, commandId=command_id)

        action_device_id = await devices_internal.resolve_device_id(action_room_id, action_device, user_id=user_id)
        req = CreateRuleRequest(
            name=name or f"{trigger_device} {trigger_kind} -> {action_device} {action_name}",
            trigger=trigger,
            action=RuleAction(deviceId=action_device_id, name=action_name, params=params or {}),
        )
        rule = await rules_internal.create_rule(req)
        return _to_json(rule.model_dump())

    return _automate_device_action


class _ListSchedulesArgs(BaseModel):
    room_id: Optional[int] = Field(None, description="특정 방의 예약만 (생략 시 전체)")
    enabled: Optional[bool] = Field(None, description="활성 예약만 필터링")


def make_list_schedules_tool(user_id: int) -> BaseTool:
    @tool("list_schedules", args_schema=_ListSchedulesArgs)
    async def _list_schedules(room_id: Optional[int] = None, enabled: Optional[bool] = None) -> str:
        """등록된 장치 예약(스케줄 룰) 목록을 조회합니다."""
        rules = await rules_internal.list_rules(enabled=enabled, has_schedule=True)
        if room_id is not None:
            room_devices = await devices_internal.list_devices(user_id=user_id, room_id=room_id)
            room_device_ids = {d.id for d in room_devices}
            rules = [r for r in rules if r.action.deviceId in room_device_ids]
        return _to_json([r.model_dump() for r in rules])

    return _list_schedules


class _CancelScheduleArgs(BaseModel):
    rule_id: str = Field(..., description="list_schedules 결과의 id")


def make_cancel_schedule_tool(user_id: int) -> BaseTool:
    @tool("cancel_schedule", args_schema=_CancelScheduleArgs)
    async def _cancel_schedule(rule_id: str) -> str:
        """등록된 장치 예약을 취소합니다."""
        await rules_internal.delete_rule(rule_id)
        return _to_json({"ok": True, "ruleId": rule_id})

    return _cancel_schedule


class _GetScheduleTasksArgs(BaseModel):
    day_of_week: Optional[str] = Field(None, description="'mon'..'sun'. weekly 일정 조회용")
    event_date: Optional[str] = Field(None, description="'YYYY-MM-DD'. 해당 날짜의 once 일정 조회용")
    schedule_kind: Optional[Literal["weekly", "once"]] = Field(None, description="생략 시 둘 다 조회")
    done: Optional[bool] = Field(None, description="완료 여부 필터")


def make_get_schedule_tasks_tool(user_id: int) -> BaseTool:
    @tool("get_schedule_tasks", args_schema=_GetScheduleTasksArgs)
    async def _get_schedule_tasks(
        day_of_week: Optional[str] = None,
        event_date: Optional[str] = None,
        schedule_kind: Optional[Literal["weekly", "once"]] = None,
        done: Optional[bool] = None,
    ) -> str:
        """사용자의 주간 반복 일정과 1회성 일정을 조회합니다."""
        tasks = await schedule_tasks_internal.get_schedule_tasks(
            user_id, day_of_week=day_of_week, event_date=event_date, schedule_kind=schedule_kind, done=done
        )
        return _to_json([t.model_dump() for t in tasks])

    return _get_schedule_tasks


_WEEKDAY_CODES: tuple[DayOfWeek, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _validate_minute_range(start_minute: Optional[int], end_minute: Optional[int]) -> None:
    """자정 기준 분(0~1440) 범위·시작<종료 순서·둘 다 함께 오는지를 확인한다. 백엔드
    (schedule_tasks_internal_store.cpp)는 이 중 아무것도 검증하지 않으므로 여기서 걸러두지
    않으면 잘못된 값이 그대로 저장된다. wave-home-front의 자체 mock 검증(validateTimeRange)이
    쓰는 규칙과 동일하게 맞춘다: 시간은 항상 짝으로 오거나 아예 없어야 한다."""
    if (start_minute is None) != (end_minute is None):
        given, missing = ("start_minute", "end_minute") if start_minute is not None else ("end_minute", "start_minute")
        raise ValueError(f"{given}를 지정했으면 {missing}도 함께 지정해야 합니다.")
    for label, value in (("start_minute", start_minute), ("end_minute", end_minute)):
        if value is not None and not (0 <= value <= 1440):
            raise ValueError(f"{label}는 0~1440 사이여야 합니다: {value}")
    if start_minute is not None and end_minute is not None and start_minute >= end_minute:
        raise ValueError(f"start_minute({start_minute})은 end_minute({end_minute})보다 작아야 합니다.")


def _derive_day_of_week(event_date: str) -> DayOfWeek:
    """once 일정의 day_of_week 는 event_date 에서 유일하게 정해지는 파생값이라
    모델에게 별도로 요구하지 않는다 — 모델이 날짜·요일을 따로 계산하다 서로 어긋나거나
    깜빡 빠뜨리면 백엔드 왕복 후에야 실패가 드러나 실패→재시도 응답이 한 번 더 늘어난다."""
    try:
        parsed = date.fromisoformat(event_date)
    except ValueError as exc:
        raise ValueError(f"event_date는 'YYYY-MM-DD' 형식이어야 합니다: {event_date!r}") from exc
    return _WEEKDAY_CODES[parsed.weekday()]


_CATEGORY_ALIASES: dict[str, ScheduleCategory] = {
    "posture": "posture",
    "sleep": "sleep",
    "diet": "diet",
    "mental": "mental",
    "life": "life",
    # Common model slips that used to fail pydantic validation mid multi-day create.
    "exercise": "posture",
    "workout": "posture",
    "fitness": "posture",
    "general": "life",
    "other": "life",
    "etc": "life",
    "daily": "life",
}


def _normalize_schedule_category(value: Any) -> ScheduleCategory:
    if not isinstance(value, str):
        raise ValueError("category는 문자열이어야 합니다.")
    key = value.strip().lower()
    mapped = _CATEGORY_ALIASES.get(key)
    if mapped is None:
        raise ValueError(
            "category는 posture|sleep|diet|mental|life 중 하나여야 합니다 "
            f"(받은 값: {value!r}). 운동은 posture, 기타는 life를 쓰세요."
        )
    return mapped


class _CreateScheduleTaskArgs(BaseModel):
    title: str = Field(..., description="일정 제목")
    category: ScheduleCategory = Field(
        ...,
        description="'posture'|'sleep'|'diet'|'mental'|'life' 중 하나. 프런트가 이 5개만 라벨로 표시한다. "
        "운동·스트레칭은 posture, 병원·행정·기타는 life.",
    )
    schedule_kind: Literal["weekly", "once"] = Field("weekly", description="weekly=매주 반복, once=1회성")
    day_of_week: Optional[DayOfWeek] = Field(
        None,
        description="'mon'..'sun'. schedule_kind='weekly'일 때만 채우세요. "
        "'once'일 때는 event_date로부터 서버가 계산하므로 생략하세요. "
        "'매일/모든 요일'이면 weekly로 mon~sun 각각 한 번씩 호출하세요(once 7개가 아님).",
    )
    event_date: Optional[str] = Field(
        None, description="schedule_kind='once'일 때 필수, 'YYYY-MM-DD'. weekly에는 넣지 마세요."
    )
    start_minute: Optional[int] = Field(None, description="자정 기준 시작 분(0~1440)")
    end_minute: Optional[int] = Field(None, description="자정 기준 종료 분(0~1440)")

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value: Any) -> ScheduleCategory:
        return _normalize_schedule_category(value)


def make_create_schedule_task_tool(user_id: int) -> BaseTool:
    @tool("create_schedule_task", args_schema=_CreateScheduleTaskArgs)
    async def _create_schedule_task(
        title: str,
        category: ScheduleCategory,
        schedule_kind: Literal["weekly", "once"] = "weekly",
        day_of_week: Optional[DayOfWeek] = None,
        event_date: Optional[str] = None,
        start_minute: Optional[int] = None,
        end_minute: Optional[int] = None,
    ) -> str:
        """새로운 반복 일정 또는 1회성 일정을 추가합니다(createdBy=agent 로 저장됨).
        once는 day_of_week를 event_date로부터 자동 계산하므로 보내지 않아도 됩니다.
        '매일/모든 요일' 요청은 schedule_kind=weekly로 day_of_week=mon..sun 을 각각 한 번씩
        호출하세요. once+날짜 7개는 쓰지 마세요."""
        category = _normalize_schedule_category(category)
        if schedule_kind == "once":
            if not event_date:
                raise ValueError("schedule_kind='once'에는 event_date('YYYY-MM-DD')가 필요합니다.")
            resolved_day_of_week = _derive_day_of_week(event_date)
        else:
            if event_date:
                raise ValueError("schedule_kind='weekly'에는 event_date를 넣을 수 없습니다.")
            if day_of_week is None:
                raise ValueError("schedule_kind='weekly'에는 day_of_week가 필요합니다.")
            resolved_day_of_week = day_of_week

        _validate_minute_range(start_minute, end_minute)

        task = await schedule_tasks_internal.create_schedule_task(
            CreateScheduleTaskRequest(
                userId=user_id,
                title=title,
                category=category,
                scheduleKind=schedule_kind,
                dayOfWeek=resolved_day_of_week,
                eventDate=event_date,
                startMinute=start_minute,
                endMinute=end_minute,
            )
        )
        return _to_json(task.model_dump())

    return _create_schedule_task


class _UpdateScheduleTaskArgs(BaseModel):
    task_id: int = Field(..., description="get_schedule_tasks 결과의 id")
    title: Optional[str] = None
    day_of_week: Optional[DayOfWeek] = None
    event_date: Optional[str] = None
    start_minute: Optional[int] = None
    end_minute: Optional[int] = None
    done: Optional[bool] = Field(None, description="완료 처리")


def make_update_schedule_task_tool(user_id: int) -> BaseTool:
    @tool("update_schedule_task", args_schema=_UpdateScheduleTaskArgs)
    async def _update_schedule_task(
        task_id: int,
        title: Optional[str] = None,
        day_of_week: Optional[DayOfWeek] = None,
        event_date: Optional[str] = None,
        start_minute: Optional[int] = None,
        end_minute: Optional[int] = None,
        done: Optional[bool] = None,
    ) -> str:
        """기존 일정의 제목/요일/날짜/시간/완료 여부를 변경합니다."""
        _validate_minute_range(start_minute, end_minute)
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if day_of_week is not None:
            fields["dayOfWeek"] = day_of_week
        if event_date is not None:
            fields["eventDate"] = event_date
        if start_minute is not None:
            fields["startMinute"] = start_minute
        if end_minute is not None:
            fields["endMinute"] = end_minute
        if done is not None:
            fields["done"] = done
        task = await schedule_tasks_internal.update_schedule_task(task_id, user_id, **fields)
        return _to_json(task.model_dump())

    return _update_schedule_task


class _DeleteScheduleTaskArgs(BaseModel):
    task_id: int = Field(..., description="get_schedule_tasks 결과의 id")


def make_delete_schedule_task_tool(user_id: int) -> BaseTool:
    @tool("delete_schedule_task", args_schema=_DeleteScheduleTaskArgs)
    async def _delete_schedule_task(task_id: int) -> str:
        """일정을 삭제합니다."""
        deleted_id = await schedule_tasks_internal.delete_schedule_task(task_id, user_id)
        return _to_json({"id": deleted_id})

    return _delete_schedule_task


class _GetAlarmsArgs(BaseModel):
    enabled: Optional[bool] = Field(None, description="활성 알람만 필터링")


def make_get_alarms_tool(user_id: int) -> BaseTool:
    @tool("get_alarms", args_schema=_GetAlarmsArgs)
    async def _get_alarms(enabled: Optional[bool] = None) -> str:
        """사용자의 알람 설정 목록을 조회합니다."""
        alarms = await alarms_internal.get_alarms(user_id, enabled=enabled)
        return _to_json([a.model_dump() for a in alarms])

    return _get_alarms


class _CreateAlarmArgs(BaseModel):
    name: str = Field(..., description="알람 이름")
    time_minute: int = Field(..., description="자정 기준 시각(분), 0~1439")
    days_of_week: list[DayOfWeek] = Field(default_factory=list, description="빈 배열=1회성 알람")
    smart_wake: bool = Field(False, description="레이더 기반 기상 맞춤 여부")


def make_create_alarm_tool(user_id: int) -> BaseTool:
    @tool("create_alarm", args_schema=_CreateAlarmArgs)
    async def _create_alarm(
        name: str, time_minute: int, days_of_week: Optional[list[DayOfWeek]] = None, smart_wake: bool = False
    ) -> str:
        """새 알람을 생성합니다. 조명/플러그/TTS 등 실행 방식(method)은 이후 update_alarm 으로 세부 설정하세요."""
        alarm = await alarms_internal.create_alarm(
            CreateAlarmRequest(
                userId=user_id, name=name, timeMinute=time_minute,
                daysOfWeek=days_of_week or [], smartWake=smart_wake,
            )
        )
        return _to_json(alarm.model_dump())

    return _create_alarm


class _UpdateAlarmArgs(BaseModel):
    alarm_id: int = Field(..., description="get_alarms 결과의 id")
    name: Optional[str] = None
    time_minute: Optional[int] = None
    days_of_week: Optional[list[DayOfWeek]] = None
    enabled: Optional[bool] = None
    tts_text: Optional[str] = Field(
        None,
        description="Wave Station 등 TTS 알람 멘트. method.type=tts 인 알람의 text만 바꿉니다.",
    )


def make_update_alarm_tool(user_id: int) -> BaseTool:
    @tool("update_alarm", args_schema=_UpdateAlarmArgs)
    async def _update_alarm(
        alarm_id: int,
        name: Optional[str] = None,
        time_minute: Optional[int] = None,
        days_of_week: Optional[list[DayOfWeek]] = None,
        enabled: Optional[bool] = None,
        tts_text: Optional[str] = None,
    ) -> str:
        """알람의 이름/시각/요일/활성 여부/TTS 멘트를 변경합니다."""
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if time_minute is not None:
            fields["timeMinute"] = time_minute
        if days_of_week is not None:
            fields["daysOfWeek"] = days_of_week
        if enabled is not None:
            fields["enabled"] = enabled
        if tts_text is not None:
            current = next(
                (a for a in await alarms_internal.get_alarms(user_id) if a.id == alarm_id),
                None,
            )
            method = current.method.model_dump() if current and current.method is not None else {}
            if method.get("type") not in (None, "tts"):
                return _to_json({
                    "error": {
                        "code": "INVALID_METHOD",
                        "message": "TTS 멘트를 바꿀 수 있는 알람이 아닙니다.",
                    }
                })
            fields["method"] = {
                "type": "tts",
                "speakerId": int(method.get("speakerId", 0)),
                "text": tts_text,
                "repeatCount": int(method.get("repeatCount", 3)),
                "intervalSec": int(method.get("intervalSec", 20)),
            }
        alarm = await alarms_internal.update_alarm(alarm_id, user_id, **fields)
        return _to_json(alarm.model_dump())

    return _update_alarm


class _DeleteAlarmArgs(BaseModel):
    alarm_id: int = Field(..., description="get_alarms 결과의 id")


def make_delete_alarm_tool(user_id: int) -> BaseTool:
    @tool("delete_alarm", args_schema=_DeleteAlarmArgs)
    async def _delete_alarm(alarm_id: int) -> str:
        """알람을 삭제합니다."""
        deleted_id = await alarms_internal.delete_alarm(alarm_id, user_id)
        return _to_json({"id": deleted_id})

    return _delete_alarm


def make_get_device_classes_tool(user_id: int) -> BaseTool:
    @tool("get_device_classes")
    async def _get_device_classes() -> str:
        """장치 class(모델군)별로 실행 가능한 action/query 목록과 특성을 조회합니다.
        특정 장치가 아니라 class 단위의 정적 능력치 카탈로그입니다."""
        classes = await devices_internal.get_device_classes()
        return _to_json([c.model_dump(by_alias=True) for c in classes])

    return _get_device_classes


class _ListIrCommandsArgs(BaseModel):
    device_hint: Optional[str] = Field(None, description="장치 힌트로 필터링 (예: 'LG 에어컨')")
    source: Optional[Literal["learned", "manual"]] = Field(None, description="학습됨/수동 등록 필터")


def make_list_ir_commands_tool(user_id: int) -> BaseTool:
    @tool("list_ir_commands", args_schema=_ListIrCommandsArgs)
    async def _list_ir_commands(
        device_hint: Optional[str] = None, source: Optional[Literal["learned", "manual"]] = None
    ) -> str:
        """등록된 IR(적외선) 명령 목록을 조회합니다. 실제 전송은 control_device 의 send_ir
        action으로 하세요(전송 전용 tool은 별도로 없습니다)."""
        commands = await rules_internal.list_ir_commands(device_hint=device_hint, source=source)
        return _to_json([c.model_dump() for c in commands])

    return _list_ir_commands


class _GetIrCommandArgs(BaseModel):
    command_id: str = Field(..., description="list_ir_commands 결과의 id")


def make_get_ir_command_tool(user_id: int) -> BaseTool:
    @tool("get_ir_command", args_schema=_GetIrCommandArgs)
    async def _get_ir_command(command_id: str) -> str:
        """IR 명령 하나의 상세 정보(원시 타이밍 포함)를 조회합니다."""
        command = await rules_internal.get_ir_command(command_id)
        return _to_json(command.model_dump())

    return _get_ir_command


class _ListEventsArgs(BaseModel):
    types: Optional[list[str]] = Field(
        None, description="이벤트 타입 필터: connection/gesture/ir/execution/schedule 중 일부"
    )
    room_id: Optional[int] = Field(None, description="특정 장치의 이벤트만 보려면 device와 함께 지정")
    device: Optional[str] = Field(None, description="장치 이름(부분 일치). room_id와 함께 지정")
    since: Optional[str] = Field(None, description="'YYYY-MM-DD HH:MM:SS' 이후 이벤트만")
    until: Optional[str] = Field(None, description="'YYYY-MM-DD HH:MM:SS' 이전 이벤트만")
    limit: int = Field(50, description="최대 200")


def make_list_events_tool(user_id: int) -> BaseTool:
    @tool("list_events", args_schema=_ListEventsArgs)
    async def _list_events(
        types: Optional[list[str]] = None,
        room_id: Optional[int] = None,
        device: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """장치 연결/제스처/IR/실행/예약 이벤트 타임라인을 조회합니다."""
        device_id = (
            await devices_internal.resolve_device_id(room_id, device, user_id=user_id)
            if room_id is not None and device is not None
            else None
        )
        events = await rules_internal.list_events(types=types, device_id=device_id, from_=since, to=until, limit=limit)
        return _to_json([e.model_dump() for e in events])

    return _list_events


class _ExecuteRuleArgs(BaseModel):
    rule_id: str = Field(
        ..., description="list_schedules 결과의 id. 지금 즉시 1회 실행합니다(예약 자체는 그대로 유지됨)."
    )


def make_execute_rule_tool(user_id: int) -> BaseTool:
    @tool("execute_rule", args_schema=_ExecuteRuleArgs)
    async def _execute_rule(rule_id: str) -> str:
        """등록된 예약/룰을 지금 즉시 한 번 실행합니다."""
        result = await rules_internal.execute_rule(rule_id)
        return _to_json(result)

    return _execute_rule


class _SetRuleEnabledArgs(BaseModel):
    rule_id: str = Field(..., description="list_schedules 결과의 id")
    enabled: bool = Field(..., description="true=활성화, false=비활성화(삭제하지 않고 잠시 꺼둠)")


def make_set_rule_enabled_tool(user_id: int) -> BaseTool:
    @tool("set_rule_enabled", args_schema=_SetRuleEnabledArgs)
    async def _set_rule_enabled(rule_id: str, enabled: bool) -> str:
        """예약/룰을 삭제하지 않고 활성화/비활성화만 전환합니다."""
        rule = await rules_internal.set_rule_enabled(rule_id, enabled)
        return _to_json(rule.model_dump())

    return _set_rule_enabled


def build_tools(user_id: int) -> list[BaseTool]:
    return [
        make_query_db_tool(user_id),
        make_rag_search_tool(),
        make_list_devices_tool(user_id),
        make_get_device_capabilities_tool(user_id),
        make_control_device_tool(user_id),
        make_query_device_tool(user_id),
        make_get_device_state_tool(user_id),
        make_get_ptz_capabilities_tool(user_id),
        make_ptz_move_tool(user_id),
        make_ptz_stop_tool(user_id),
        make_ptz_zoom_tool(user_id),
        make_get_camera_stream_tool(user_id),
        make_set_camera_stream_tool(user_id),
        make_send_camera_tts_tool(user_id),
        make_schedule_device_action_tool(user_id),
        make_automate_device_action_tool(user_id),
        make_list_schedules_tool(user_id),
        make_cancel_schedule_tool(user_id),
        make_get_schedule_tasks_tool(user_id),
        make_create_schedule_task_tool(user_id),
        make_update_schedule_task_tool(user_id),
        make_delete_schedule_task_tool(user_id),
        make_get_alarms_tool(user_id),
        make_create_alarm_tool(user_id),
        make_update_alarm_tool(user_id),
        make_delete_alarm_tool(user_id),
        make_get_device_classes_tool(user_id),
        make_list_ir_commands_tool(user_id),
        make_get_ir_command_tool(user_id),
        make_list_events_tool(user_id),
        make_execute_rule_tool(user_id),
        make_set_rule_enabled_tool(user_id),
    ]


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
