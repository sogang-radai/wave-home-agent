"""Mock implementation of docs/api.md §2.1 POST /internal/v1/db/query.

The real C++ backend doesn't expose /internal/v1/* yet, so this module returns
canned data shaped exactly like the wire contract (camelCase field names,
matching api.md's own examples even though docs/db_updated.md's DB columns are
snake_case). Swapping in real HTTP calls later only touches `_run_one`.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.clients.core import CoreApiClient
from app.config import get_settings


MAX_QUERIES = 10
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


class DbQuery(BaseModel):
    table: str
    filter: dict[str, Any] = Field(default_factory=dict)
    limit: int = DEFAULT_LIMIT
    order: Literal["asc", "desc"] = "asc"


class DbQueryError(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class DbQueryResultItem(BaseModel):
    table: str
    count: int
    items: list[dict[str, Any]]
    error: Optional[DbQueryError] = None


class _TableSpec(BaseModel):
    required_any: set[str] = Field(default_factory=set)
    """At least one of these filter keys must be present (empty = no requirement)."""
    allowed: set[str] = Field(default_factory=set)
    mock_items: "list[dict[str, Any]] | None" = None


def _sleep_session_mock(user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 4001,
            "userId": user_id,
            "roomId": 2,
            "nightDate": "2026-07-05",
            "onset": "2026-07-05 23:40:00",
            "finalWake": "2026-07-06 06:35:00",
            "timeInBedMinutes": 450,
            "actualSleepMinutes": 415,
            "efficiency": 0.92,
            "wakeUps": 3,
            "hrMean": 62.0,
        }
    ]


def _sleep_stat_mock(user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 91201,
            "userId": user_id,
            "sessionId": 4001,
            "granularity": "30m",
            "timeStart": "2026-07-06 03:00:00",
            "timeEnd": "2026-07-06 03:30:00",
            "stageLabel": "deep",
            "hrMean": 60.5,
        }
    ]


def _sleep_report_mock(user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 812,
            "userId": user_id,
            "period": "weekly",
            "periodStart": "2026-06-29",
            "metrics": {"averageScore": 74, "avgSleepMinutes": 402, "wakeUps": 3},
        }
    ]


def _daily_user_model_mock(user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 501,
            "userId": user_id,
            "modelDate": "2026-07-25",
            "windowDays": 14,
            "avgBedtimeMinute": 1430,  # 23:50
            "avgWakeMinute": 400,      # 06:40
            "sleepDurationAvgMinutes": 405.0,
            "preferredLightBrightness": 42.0,
            "sampleDays": 12,
            "computedAt": "2026-07-26 00:05:00",
        }
    ]


MOCK_USER_HABITS: list[dict[str, Any]] = [
    {
        "id": 1,
        "userId": 1,
        "habitType": "sleep",
        "title": "취침 전 침실 조명을 끈다",
        "description": "최근 14일 중 12일, 취침 시각 무렵 침실 조명을 끄는 행동이 반복 관찰되었습니다.",
        "confidence": 0.86,
        "windowDays": 14,
        "status": "active",
        "lastVerifiedAt": "2026-07-26 00:05:00",
        "lastUsedAt": None,
    },
]


def _user_habit_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_USER_HABITS
    if "userId" in filter_:
        items = [h for h in items if h["userId"] == filter_["userId"]]
    if "status" in filter_:
        items = [h for h in items if h["status"] == filter_["status"]]
    if "habitType" in filter_:
        items = [h for h in items if h["habitType"] == filter_["habitType"]]
    if "id" in filter_:
        items = [h for h in items if h["id"] == filter_["id"]]
    return items


MOCK_HOME_EVENTS: list[dict[str, Any]] = [
    {
        "id": 175,
        "userId": 1,
        "type": "gesture",
        "occurredAt": "2026-06-30 23:54:16",
        "deviceId": 6,
        "deviceName": "침실 조명",
        "message": "제스처(circle_cw)로 침실 조명 brightness_up 실행",
        "triggeredBy": "gesture",
        "detailJson": '{"action":"brightness","params":{"value":70}}',
    },
    {
        "id": 174,
        "userId": 1,
        "type": "schedule",
        "occurredAt": "2026-06-30 23:00:03",
        "deviceId": 6,
        "deviceName": "침실 조명",
        "message": "취침 시간 자동 소등 규칙이 실행되어 침실 조명을 껐습니다.",
        "triggeredBy": "rule:1",
        "detailJson": '{"action":"off","params":{}}',
    },
]


def _home_event_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_HOME_EVENTS
    if "userId" in filter_:
        items = [e for e in items if e["userId"] == filter_["userId"]]
    if "type" in filter_:
        items = [e for e in items if e["type"] == filter_["type"]]
    if "deviceId" in filter_:
        items = [e for e in items if e["deviceId"] == filter_["deviceId"]]
    if "id" in filter_:
        items = [e for e in items if e["id"] == filter_["id"]]
    date_from = filter_.get("from")
    date_to = filter_.get("to")
    if date_from:
        items = [e for e in items if e["occurredAt"] >= date_from]
    if date_to:
        items = [e for e in items if e["occurredAt"] <= date_to]
    return items


# 별개 기능(추후 작업)에서 쓸 user_action_log 용 임시 mock — 다른 테이블처럼 mock.db 실 시딩
# 데이터가 없어 그럴싸한 가짜 행 몇 개만 둔다. schedule_task_mock 과 동일하게 filter-aware.
# category 는 goal-coaching 기능(app/graph/goal_coaching_graph.py)이 추가한 NEW 컬럼 —
# ref_type='schedule_task' 인 행에만 그 schedule_task.category 값이 채워지고,
# ref_type='insight' 인 행은 카테고리 개념이 없어 항상 None 이다(MOCK_SCHEDULE_TASKS의
# 해당 id 의 category 와 일치시켰다: id=1 -> "posture", id=20 -> "diet").
MOCK_USER_ACTION_LOGS: list[dict[str, Any]] = [
    {"id": 1, "userId": 1, "actionType": "insight_applied", "refType": "insight", "refId": 2001,
     "occurredAt": "2026-07-09 08:15:00", "category": None, "metadataJson": None},
    {"id": 2, "userId": 1, "actionType": "schedule_task_completed", "refType": "schedule_task", "refId": 1,
     "occurredAt": "2026-07-10 07:05:00", "category": "posture", "metadataJson": None},
    {"id": 3, "userId": 2, "actionType": "schedule_task_created", "refType": "schedule_task", "refId": 20,
     "occurredAt": "2026-07-10 21:40:00", "category": "diet", "metadataJson": None},
]


def _user_action_log_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_USER_ACTION_LOGS
    if "userId" in filter_:
        items = [a for a in items if a["userId"] == filter_["userId"]]
    if "actionType" in filter_:
        items = [a for a in items if a["actionType"] == filter_["actionType"]]
    if "refType" in filter_:
        items = [a for a in items if a["refType"] == filter_["refType"]]
    if "refId" in filter_:
        items = [a for a in items if a["refId"] == filter_["refId"]]
    if "category" in filter_:
        items = [a for a in items if a.get("category") == filter_["category"]]
    if "id" in filter_:
        items = [a for a in items if a["id"] == filter_["id"]]
    date_from = filter_.get("from")
    date_to = filter_.get("to")
    if date_from:
        items = [a for a in items if a["occurredAt"] >= date_from]
    if date_to:
        items = [a for a in items if a["occurredAt"] <= date_to]
    return items


# 프로젝트 루트 mock.db의 schedule_task 실 시딩 데이터(26행, user 1: 16행/user 2: 10행)를
# 그대로 옮겨온 것 — 아래 _schedule_task_mock 은 예전엔 이걸 안 읽고 가짜 행 1개만 리턴해서,
# 실제로는 데이터가 있는데도 인사이트 생성 시 "계획 데이터가 확인되지 않습니다"로 나오는
# 원인이었다(mock.db 자체는 코드에서 열지 않으므로 여기 하드코딩이 유일한 소스).
MOCK_SCHEDULE_TASKS: list[dict[str, Any]] = [
    {"id": 1, "userId": 1, "title": "아침 스트레칭", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "posture", "scheduleKind": "weekly", "dayOfWeek": "mon", "eventDate": None,
     "startMinute": 420, "endMinute": 435, "done": False, "sourceInsightId": None},
    {"id": 2, "userId": 1, "title": "아침 스트레칭", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "posture", "scheduleKind": "weekly", "dayOfWeek": "tue", "eventDate": None,
     "startMinute": 420, "endMinute": 435, "done": False, "sourceInsightId": None},
    {"id": 3, "userId": 1, "title": "아침 스트레칭", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "posture", "scheduleKind": "weekly", "dayOfWeek": "wed", "eventDate": None,
     "startMinute": 420, "endMinute": 435, "done": False, "sourceInsightId": None},
    {"id": 4, "userId": 1, "title": "아침 스트레칭", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "posture", "scheduleKind": "weekly", "dayOfWeek": "thu", "eventDate": None,
     "startMinute": 420, "endMinute": 435, "done": False, "sourceInsightId": None},
    {"id": 5, "userId": 1, "title": "아침 스트레칭", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "posture", "scheduleKind": "weekly", "dayOfWeek": "fri", "eventDate": None,
     "startMinute": 420, "endMinute": 435, "done": False, "sourceInsightId": None},
    {"id": 6, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "mon", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 7, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "tue", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 8, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "wed", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 9, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "thu", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 10, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "fri", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 11, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "sat", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 12, "userId": 1, "title": "취침 전 독서", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "sun", "eventDate": None,
     "startMinute": 1350, "endMinute": 1380, "done": False, "sourceInsightId": None},
    {"id": 13, "userId": 1, "title": "주말 명상", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "sat", "eventDate": None,
     "startMinute": 540, "endMinute": 560, "done": False, "sourceInsightId": None},
    {"id": 14, "userId": 1, "title": "주말 명상", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "mental", "scheduleKind": "weekly", "dayOfWeek": "sun", "eventDate": None,
     "startMinute": 540, "endMinute": 560, "done": False, "sourceInsightId": None},
    {"id": 15, "userId": 1, "title": "치과 정기검진", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "life", "scheduleKind": "once", "dayOfWeek": "tue", "eventDate": "2026-06-16",
     "startMinute": 840, "endMinute": 900, "done": False, "sourceInsightId": None},
    {"id": 16, "userId": 1, "title": "여름 옷 정리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "life", "scheduleKind": "once", "dayOfWeek": "sat", "eventDate": "2026-06-20",
     "startMinute": 600, "endMinute": 690, "done": False, "sourceInsightId": None},
    {"id": 17, "userId": 2, "title": "헬스장 운동", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "fitness", "scheduleKind": "weekly", "dayOfWeek": "mon", "eventDate": None,
     "startMinute": 1140, "endMinute": 1230, "done": False, "sourceInsightId": None},
    {"id": 18, "userId": 2, "title": "헬스장 운동", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "fitness", "scheduleKind": "weekly", "dayOfWeek": "wed", "eventDate": None,
     "startMinute": 1140, "endMinute": 1230, "done": False, "sourceInsightId": None},
    {"id": 19, "userId": 2, "title": "헬스장 운동", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "fitness", "scheduleKind": "weekly", "dayOfWeek": "fri", "eventDate": None,
     "startMinute": 1140, "endMinute": 1230, "done": False, "sourceInsightId": None},
    {"id": 20, "userId": 2, "title": "저녁 식단 관리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "diet", "scheduleKind": "weekly", "dayOfWeek": "mon", "eventDate": None,
     "startMinute": 1080, "endMinute": 1110, "done": False, "sourceInsightId": None},
    {"id": 21, "userId": 2, "title": "저녁 식단 관리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "diet", "scheduleKind": "weekly", "dayOfWeek": "tue", "eventDate": None,
     "startMinute": 1080, "endMinute": 1110, "done": False, "sourceInsightId": None},
    {"id": 22, "userId": 2, "title": "저녁 식단 관리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "diet", "scheduleKind": "weekly", "dayOfWeek": "wed", "eventDate": None,
     "startMinute": 1080, "endMinute": 1110, "done": False, "sourceInsightId": None},
    {"id": 23, "userId": 2, "title": "저녁 식단 관리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "diet", "scheduleKind": "weekly", "dayOfWeek": "thu", "eventDate": None,
     "startMinute": 1080, "endMinute": 1110, "done": False, "sourceInsightId": None},
    {"id": 24, "userId": 2, "title": "저녁 식단 관리", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "diet", "scheduleKind": "weekly", "dayOfWeek": "fri", "eventDate": None,
     "startMinute": 1080, "endMinute": 1110, "done": False, "sourceInsightId": None},
    {"id": 25, "userId": 2, "title": "주말 등산", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "fitness", "scheduleKind": "weekly", "dayOfWeek": "sat", "eventDate": None,
     "startMinute": 480, "endMinute": 660, "done": False, "sourceInsightId": None},
    {"id": 26, "userId": 2, "title": "헬스 PT 상담", "createdAt": "2026-05-20 09:00:00", "createdBy": "user",
     "category": "fitness", "scheduleKind": "once", "dayOfWeek": "fri", "eventDate": "2026-06-05",
     "startMinute": 1230, "endMinute": 1260, "done": False, "sourceInsightId": None},
]


def _schedule_task_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_SCHEDULE_TASKS
    if "userId" in filter_:
        items = [t for t in items if t["userId"] == filter_["userId"]]
    if "category" in filter_:
        items = [t for t in items if t["category"] == filter_["category"]]
    if "scheduleKind" in filter_:
        items = [t for t in items if t["scheduleKind"] == filter_["scheduleKind"]]
    if "dayOfWeek" in filter_:
        items = [t for t in items if t["dayOfWeek"] == filter_["dayOfWeek"]]
    if "done" in filter_:
        items = [t for t in items if t["done"] == filter_["done"]]
    if "createdBy" in filter_:
        items = [t for t in items if t["createdBy"] == filter_["createdBy"]]
    if "sourceInsightId" in filter_:
        items = [t for t in items if t["sourceInsightId"] == filter_["sourceInsightId"]]
    if "id" in filter_:
        items = [t for t in items if t["id"] == filter_["id"]]
    # eventDate 는 'once' 작업에만 있다 — from/to 로 그 기간에 걸리는 1회성 일정만 좁히고,
    # 매주 반복되는 'weekly' 작업은 특정 날짜가 없으니 날짜 필터로 걸러내지 않는다.
    date_from = filter_.get("from")
    date_to = filter_.get("to")
    if date_from or date_to:
        def _in_range(t: dict[str, Any]) -> bool:
            if t["scheduleKind"] == "weekly":
                return True
            event_date = t["eventDate"]
            if event_date is None:
                return True
            if date_from and event_date < date_from:
                return False
            if date_to and event_date > date_to:
                return False
            return True

        items = [t for t in items if _in_range(t)]
    if "eventDate" in filter_:
        items = [t for t in items if t["eventDate"] == filter_["eventDate"]]
    return items


# 위와 동일한 이유(mock.db 시딩 데이터 미반영)로 weekly_plan_report 도 예전엔 generator
# 등록 자체가 빠져 있어 항상 count=0 이었다. mock.db 의 2026-06-22~06-30(user 1/2, 총 18행)를 옮겨온다.
MOCK_WEEKLY_PLAN_REPORTS: list[dict[str, Any]] = [
    {"id": 43, "userId": 1, "periodStart": "2026-06-22", "headline": "최근 7일 평균 수면 점수 77.0점", "reportText": "2026-06-16~2026-06-22(7일) 동안 평균 수면 점수는 77.0점, 평균 수면 효율은 90.0% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-16: 낮 치과 정기검진 후 약간 긴장, 평범한 밤 / 06-17: 무더위 시작 전 마지막 쾌적한 밤, B구간 마감 / 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료. 평균 가정 전력 사용량은 하루 5.67kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 45, "userId": 1, "periodStart": "2026-06-23", "headline": "최근 7일 평균 수면 점수 77.9점", "reportText": "2026-06-17~2026-06-23(7일) 동안 평균 수면 점수는 77.9점, 평균 수면 효율은 90.3% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-17: 무더위 시작 전 마지막 쾌적한 밤, B구간 마감 / 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료. 평균 가정 전력 사용량은 하루 6.72kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 47, "userId": 1, "periodStart": "2026-06-24", "headline": "최근 7일 평균 수면 점수 78.3점", "reportText": "2026-06-18~2026-06-24(7일) 동안 평균 수면 점수는 78.3점, 평균 수면 효율은 90.4% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감. 평균 가정 전력 사용량은 하루 6.84kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 49, "userId": 1, "periodStart": "2026-06-25", "headline": "최근 7일 평균 수면 점수 77.1점", "reportText": "2026-06-19~2026-06-25(7일) 동안 평균 수면 점수는 77.1점, 평균 수면 효율은 90.0% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수. 평균 가정 전력 사용량은 하루 7.21kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 51, "userId": 1, "periodStart": "2026-06-26", "headline": "최근 7일 평균 수면 점수 76.9점", "reportText": "2026-06-20~2026-06-26(7일) 동안 평균 수면 점수는 76.9점, 평균 수면 효율은 89.9% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중. 평균 가정 전력 사용량은 하루 7.17kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 53, "userId": 1, "periodStart": "2026-06-27", "headline": "최근 7일 평균 수면 점수 77.7점", "reportText": "2026-06-21~2026-06-27(7일) 동안 평균 수면 점수는 77.7점, 평균 수면 효율은 90.2% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복. 평균 가정 전력 사용량은 하루 7.15kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 55, "userId": 1, "periodStart": "2026-06-28", "headline": "최근 7일 평균 수면 점수 78.9점", "reportText": "2026-06-22~2026-06-28(7일) 동안 평균 수면 점수는 78.9점, 평균 수면 효율은 90.6% 였어요. 지난 기간과 비교하면 개선되고 있어요. 이 기간 특이사항: 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작. 평균 가정 전력 사용량은 하루 8.11kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 57, "userId": 1, "periodStart": "2026-06-29", "headline": "최근 7일 평균 수면 점수 79.7점", "reportText": "2026-06-23~2026-06-29(7일) 동안 평균 수면 점수는 79.7점, 평균 수면 효율은 90.9% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작 / 06-29: 한 달 중 최고 컨디션. 평균 가정 전력 사용량은 하루 7.58kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 59, "userId": 1, "periodStart": "2026-06-30", "headline": "최근 7일 평균 수면 점수 80.3점", "reportText": "2026-06-24~2026-06-30(7일) 동안 평균 수면 점수는 80.3점, 평균 수면 효율은 91.1% 였어요. 지난 기간과 비교하면 비슷한 수준을 유지하고 있어요. 이 기간 특이사항: 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작 / 06-29: 한 달 중 최고 컨디션 / 06-30: 월말 마무리 - 전반적 개선 추세로 마감. 평균 가정 전력 사용량은 하루 6.56kWh 였습니다. 아침 스트레칭과 취침 전 독서 루틴을 계속 유지해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 44, "userId": 2, "periodStart": "2026-06-22", "headline": "최근 7일 평균 가정 전력 5.67kWh/일", "reportText": "2026-06-16~2026-06-22(7일) 동안 가정 평균 전력 사용량은 하루 5.67kWh로 지난 기간보다 비슷했어요. 이 기간 특이사항: 06-16: 낮 치과 정기검진 후 약간 긴장, 평범한 밤 / 06-17: 무더위 시작 전 마지막 쾌적한 밤, B구간 마감 / 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 46, "userId": 2, "periodStart": "2026-06-23", "headline": "최근 7일 평균 가정 전력 6.72kWh/일", "reportText": "2026-06-17~2026-06-23(7일) 동안 가정 평균 전력 사용량은 하루 6.72kWh로 지난 기간보다 늘었어요. 이 기간 특이사항: 06-17: 무더위 시작 전 마지막 쾌적한 밤, B구간 마감 / 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 48, "userId": 2, "periodStart": "2026-06-24", "headline": "최근 7일 평균 가정 전력 6.84kWh/일", "reportText": "2026-06-18~2026-06-24(7일) 동안 가정 평균 전력 사용량은 하루 6.84kWh로 지난 기간보다 비슷했어요. 이 기간 특이사항: 06-18: 폭염 - 입면 지연, 깊은 수면 급감, 뒤척임 증가 / 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 50, "userId": 2, "periodStart": "2026-06-25", "headline": "최근 7일 평균 가정 전력 7.21kWh/일", "reportText": "2026-06-19~2026-06-25(7일) 동안 가정 평균 전력 사용량은 하루 7.21kWh로 지난 기간보다 늘었어요. 이 기간 특이사항: 06-19: 에어컨 강화 가동, 서서히 회복 / 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 52, "userId": 2, "periodStart": "2026-06-26", "headline": "최근 7일 평균 가정 전력 7.17kWh/일", "reportText": "2026-06-20~2026-06-26(7일) 동안 가정 평균 전력 사용량은 하루 7.17kWh로 지난 기간보다 비슷했어요. 이 기간 특이사항: 06-20: 주말, 여름 옷 정리 후 무난한 밤 / 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 54, "userId": 2, "periodStart": "2026-06-27", "headline": "최근 7일 평균 가정 전력 7.15kWh/일", "reportText": "2026-06-21~2026-06-27(7일) 동안 가정 평균 전력 사용량은 하루 7.15kWh로 지난 기간보다 비슷했어요. 이 기간 특이사항: 06-21: 회복 지속 / 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 56, "userId": 2, "periodStart": "2026-06-28", "headline": "최근 7일 평균 가정 전력 8.11kWh/일", "reportText": "2026-06-22~2026-06-28(7일) 동안 가정 평균 전력 사용량은 하루 8.11kWh로 지난 기간보다 늘었어요. 이 기간 특이사항: 06-22: 적응 완료 / 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 58, "userId": 2, "periodStart": "2026-06-29", "headline": "최근 7일 평균 가정 전력 7.58kWh/일", "reportText": "2026-06-23~2026-06-29(7일) 동안 가정 평균 전력 사용량은 하루 7.58kWh로 지난 기간보다 줄었어요. 이 기간 특이사항: 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작 / 06-29: 한 달 중 최고 컨디션. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
    {"id": 60, "userId": 2, "periodStart": "2026-06-30", "headline": "최근 7일 평균 가정 전력 6.56kWh/일", "reportText": "2026-06-24~2026-06-30(7일) 동안 가정 평균 전력 사용량은 하루 6.56kWh로 지난 기간보다 줄었어요. 이 기간 특이사항: 06-24: C구간 회복 후 최고점, C구간 마감 / 06-25: 저녁 모임으로 늦은 취침 - 짧은 수면, 최저 점수 / 06-26: 전날 여파, 피로 회복 중 / 06-27: 주말 장수면으로 회복 / 06-28: 완전 회복, E구간 시작 / 06-29: 한 달 중 최고 컨디션 / 06-30: 월말 마무리 - 전반적 개선 추세로 마감. 헬스장·식단 루틴을 꾸준히 지키고 계세요. 저녁 시간 인덕션 사용에 주의해보세요.", "createdAt": "2026-07-01 00:00:00"},
]


def _weekly_plan_report_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_WEEKLY_PLAN_REPORTS
    if "userId" in filter_:
        items = [r for r in items if r["userId"] == filter_["userId"]]
    if "periodStart" in filter_:
        items = [r for r in items if r["periodStart"] == filter_["periodStart"]]
    date_from = filter_.get("from")
    date_to = filter_.get("to")
    if date_from:
        items = [r for r in items if r["periodStart"] >= date_from]
    if date_to:
        items = [r for r in items if r["periodStart"] <= date_to]
    if "id" in filter_:
        items = [r for r in items if r["id"] == filter_["id"]]
    return items


# device-tool-api.md §설계 원칙 4: roomId+장치이름 해석은 device/device_room_map 조회로 처리한다.
# Phase 3의 devices_internal.resolve_device_id() 가 mock 모드에서도 id/이름이 어긋나지 않도록
# 이 카탈로그를 그대로 import 해서 재사용한다.
#
# id/room/user 체계는 프로젝트 루트의 mock.db(db-schema.md 그대로 채워진 실 시딩 데이터, 2 유저·
# 3 방·13 장치)와 1:1로 맞췄다 — 나중에 실제 백엔드가 이 mock.db로 시딩되면 여기 테스트/데모 id가
# 그대로 들어맞는다. automation_rule/alarm 은 mock.db 쪽 데이터가 지금 스펙(cron 미지원 RuleSchedule,
# AlarmMethod 에 sound 없음 등)과 안 맞아서 가져오지 않았다 — 팀 확인 필요, rules_internal.py/
# alarms_internal.py 의 기존 mock은 그대로 둔다.
MOCK_DEVICES: list[dict[str, Any]] = [
    {"id": 1, "name": "침실 하방 레이더", "description": "침대 하부 mmWave 레이더",
     "class": "srs_r4sn", "archived": 0, "roomId": 2},
    {"id": 2, "name": "침실 책상 레이더", "description": "책상 mmWave 레이더",
     "class": "srs_r4sn", "archived": 0, "roomId": 2},
    {"id": 3, "name": "Wave Station", "description": "IR 허브·환경·마이크",
     "class": "wave_station", "archived": 0, "roomId": 2},
    {"id": 4, "name": "폰 카메라", "description": "DroidCam", "class": "droid_cam", "archived": 0, "roomId": 1},
    {"id": 5, "name": "거실 카메라", "description": "Reolink E1 Pro",
     "class": "reolink_e1_pro", "archived": 0, "roomId": 1},
    {"id": 6, "name": "플러그1 - 선풍기", "description": "거실 선풍기 플러그",
     "class": "tuya_ep2h", "archived": 0, "roomId": 1},
    {"id": 7, "name": "플러그2 - 컴퓨터", "description": "침실 PC 플러그",
     "class": "tuya_ep2h", "archived": 0, "roomId": 2},
    {"id": 8, "name": "플러그3 - 에어컨", "description": "침실 에어컨 플러그",
     "class": "tuya_ep2h", "archived": 0, "roomId": 2},
    {"id": 9, "name": "플러그4 - 인덕션", "description": "부엌 인덕션 플러그",
     "class": "tuya_ep2h", "archived": 0, "roomId": 3},
    {"id": 10, "name": "침실 TV", "description": "삼성 Tizen TV (G7)",
     "class": "samsung_g7", "archived": 0, "roomId": 2},
    {"id": 11, "name": "침실 조명", "description": "WiZ 컬러 조명",
     "class": "philips_wiz_e29_color", "archived": 0, "roomId": 2},
    {"id": 12, "name": "거실 조명", "description": "WiZ 화이트 조명",
     "class": "philips_wiz_e29_white", "archived": 0, "roomId": 1},
    {"id": 13, "name": "부엌 조명", "description": "WiZ 화이트 조명",
     "class": "philips_wiz_e29_white", "archived": 0, "roomId": 3},
    {"id": 14, "name": "플러그5 - 전자레인지", "description": "부엌 전자레인지 플러그",
     "class": "tuya_ep2h", "archived": 0, "roomId": 3},
]

MOCK_DEVICE_ROOM_MAP: list[dict[str, Any]] = [
    {"deviceId": d["id"], "roomId": d["roomId"]} for d in MOCK_DEVICES
]

MOCK_ROOMS: list[dict[str, Any]] = [
    {"id": 1, "name": "거실", "description": "공용 거실. 카메라/에어컨/선풍기/조명, 두 사람 모두 사용."},
    {"id": 2, "name": "침실", "description": "김건강 침실. 레이더 2대(하방/책상)/Wave Station/조명/TV/PC 플러그. 박헬스는 사용하지 않음."},
    {"id": 3, "name": "부엌", "description": "공용 부엌. 인덕션·전자레인지 플러그/조명, 두 사람 모두 사용."},
]

# user 1 = 김건강(거실·침실·부엌 전부), user 2 = 박헬스(거실·부엌만, 침실은 안 씀) — mock.db 그대로.
MOCK_ROOM_USER_MAP: list[dict[str, Any]] = [
    {"roomId": 1, "userId": 1},
    {"roomId": 2, "userId": 1},
    {"roomId": 3, "userId": 1},
    {"roomId": 1, "userId": 2},
    {"roomId": 3, "userId": 2},
]

# 공용 장치(거실·부엌 대부분)는 두 유저 다 접근, 침실 장치는 user 1 전용 — mock.db 그대로.
MOCK_DEVICE_USER_MAP: list[dict[str, Any]] = [
    {"deviceId": 1, "userId": 1},
    {"deviceId": 2, "userId": 1},
    {"deviceId": 3, "userId": 1},
    {"deviceId": 4, "userId": 1}, {"deviceId": 4, "userId": 2},
    {"deviceId": 5, "userId": 1}, {"deviceId": 5, "userId": 2},
    {"deviceId": 6, "userId": 1}, {"deviceId": 6, "userId": 2},
    {"deviceId": 7, "userId": 1},
    {"deviceId": 8, "userId": 1},
    {"deviceId": 9, "userId": 1}, {"deviceId": 9, "userId": 2},
    {"deviceId": 10, "userId": 1},
    {"deviceId": 11, "userId": 1},
    {"deviceId": 12, "userId": 1}, {"deviceId": 12, "userId": 2},
    {"deviceId": 13, "userId": 1}, {"deviceId": 13, "userId": 2},
    {"deviceId": 14, "userId": 1}, {"deviceId": 14, "userId": 2},
]


def _device_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_DEVICES
    if "roomId" in filter_:
        items = [d for d in items if d["roomId"] == filter_["roomId"]]
    if "class" in filter_:
        items = [d for d in items if d["class"] == filter_["class"]]
    if "archived" in filter_:
        items = [d for d in items if d["archived"] == filter_["archived"]]
    if "id" in filter_:
        items = [d for d in items if d["id"] == filter_["id"]]
    if "userId" in filter_:
        owned = {m["deviceId"] for m in MOCK_DEVICE_USER_MAP if m["userId"] == filter_["userId"]}
        items = [d for d in items if d["id"] in owned]
    return items


def _device_room_map_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_DEVICE_ROOM_MAP
    if "roomId" in filter_:
        items = [m for m in items if m["roomId"] == filter_["roomId"]]
    if "deviceId" in filter_:
        items = [m for m in items if m["deviceId"] == filter_["deviceId"]]
    return items


def _device_user_map_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_DEVICE_USER_MAP
    if "deviceId" in filter_:
        items = [m for m in items if m["deviceId"] == filter_["deviceId"]]
    if "userId" in filter_:
        items = [m for m in items if m["userId"] == filter_["userId"]]
    return items


def _room_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_ROOMS
    if "id" in filter_:
        items = [r for r in items if r["id"] == filter_["id"]]
    if "userId" in filter_:
        owned = {m["roomId"] for m in MOCK_ROOM_USER_MAP if m["userId"] == filter_["userId"]}
        items = [r for r in items if r["id"] in owned]
    return items


def _room_user_map_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_ROOM_USER_MAP
    if "roomId" in filter_:
        items = [m for m in items if m["roomId"] == filter_["roomId"]]
    if "userId" in filter_:
        items = [m for m in items if m["userId"] == filter_["userId"]]
    return items


# goal-coaching 기능(app/graph/goal_coaching_graph.py)용 임시 mock — user_action_log 와
# 마찬가지로 mock.db 실 시딩 데이터가 없어 그럴싸한 가짜 행 몇 개만 둔다. MOCK_SCHEDULE_TASKS의
# posture/mental 루틴과 이어지도록 골랐다(취침 전 독서 -> "취침 11시 전에 자기").
MOCK_GOALS: list[dict[str, Any]] = [
    {"id": 1, "userId": 1, "title": "취침 11시 전에 자기", "category": "sleep", "status": "active",
     "createdAt": "2026-06-10 21:00:00", "updatedAt": "2026-06-10 21:00:00"},
    {"id": 2, "userId": 1, "title": "아침 스트레칭 매일 하기", "category": "posture", "status": "active",
     "createdAt": "2026-06-15 08:00:00", "updatedAt": "2026-06-15 08:00:00"},
]


def _goal_mock(_user_id: int | None, filter_: dict[str, Any]) -> list[dict[str, Any]]:
    items = MOCK_GOALS
    if "userId" in filter_:
        items = [g for g in items if g["userId"] == filter_["userId"]]
    if "status" in filter_:
        items = [g for g in items if g["status"] == filter_["status"]]
    if "category" in filter_:
        items = [g for g in items if g["category"] == filter_["category"]]
    if "id" in filter_:
        items = [g for g in items if g["id"] == filter_["id"]]
    return items


TABLE_SPECS: dict[str, _TableSpec] = {
    "user": _TableSpec(allowed={"id"}),
    "room": _TableSpec(allowed={"id", "userId"}),
    "room_user_map": _TableSpec(required_any={"roomId", "userId"}, allowed={"roomId", "userId"}),
    "device": _TableSpec(allowed={"id", "class", "archived", "roomId", "userId"}),
    "device_user_map": _TableSpec(required_any={"deviceId", "userId"}, allowed={"deviceId", "userId"}),
    "device_room_map": _TableSpec(required_any={"deviceId", "roomId"}, allowed={"deviceId", "roomId"}),
    "sleep_session": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "roomId", "nightDate", "from", "to"},
    ),
    "sleep_stat": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "sessionId", "roomId", "granularity", "from", "to"},
    ),
    "sleep_report": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "period", "periodStart", "from", "to"},
    ),
    "power_energy": _TableSpec(allowed={"deviceId", "id", "granularity", "from", "to", "roomId", "userId"}),
    "power_report": _TableSpec(
        allowed={"deviceId", "id", "energyId", "period", "periodStart", "from", "to", "roomId", "userId"}
    ),
    "gesture_set": _TableSpec(allowed={"id", "archived"}),
    "gesture_log": _TableSpec(allowed={"gestureSetId", "radarId", "deviceId", "classId", "from", "to"}),
    "schedule_task": _TableSpec(
        required_any={"userId"},
        allowed={
            "id", "userId", "category", "scheduleKind", "dayOfWeek", "eventDate",
            "from", "to", "done", "createdBy", "sourceInsightId",
        },
    ),
    "automation_rule": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "externalId", "enabled", "hasTrigger", "hasSchedule", "from", "to"},
    ),
    "alarm": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "enabled", "smartWake", "deviceId", "radarDeviceId", "from", "to"},
    ),
    # posture_stat/posture_report: db-query-api.md 가 "스펙 초안"이라 명시 — 최소 필드만.
    "posture_stat": _TableSpec(required_any={"userId"}, allowed={"userId", "granularity", "from", "to"}),
    "posture_report": _TableSpec(
        required_any={"userId"},
        allowed={"userId", "period", "periodStart", "from", "to"},
    ),
    "weekly_plan_report": _TableSpec(required_any={"userId"}, allowed={"userId", "periodStart", "from", "to"}),
    "notification": _TableSpec(required_any={"userId"}, allowed={"id", "userId", "type", "read", "from", "to"}),
    "chat_history": _TableSpec(required_any={"userId"}, allowed={"id", "userId", "from", "to"}),
    "insight": _TableSpec(
        required_any={"userId"},
        allowed={
            "id", "userId", "surface", "kind", "date", "actionable", "actionType", "approved", "from", "to",
        },
    ),
    "user_action_log": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "actionType", "refType", "refId", "category", "from", "to"},
    ),
    "goal": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "status", "category"},
    ),
    "daily_user_model": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "modelDate", "from", "to"},
    ),
    "user_habit": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "status", "habitType", "from", "to"},
    ),
    "home_event": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "type", "deviceId", "from", "to"},
    ),
}

_MOCK_GENERATORS = {
    "sleep_session": _sleep_session_mock,
    "sleep_stat": _sleep_stat_mock,
    "sleep_report": _sleep_report_mock,
    "daily_user_model": _daily_user_model_mock,
}

# device/device_room_map/device_user_map/room/room_user_map/schedule_task/weekly_plan_report
# 목업은 filter 를 참조해야 해서 별도 딕셔너리로 분리.
_FILTER_AWARE_MOCK_GENERATORS = {
    "device": _device_mock,
    "device_room_map": _device_room_map_mock,
    "device_user_map": _device_user_map_mock,
    "room": _room_mock,
    "room_user_map": _room_user_map_mock,
    "schedule_task": _schedule_task_mock,
    "weekly_plan_report": _weekly_plan_report_mock,
    "user_action_log": _user_action_log_mock,
    "goal": _goal_mock,
    "user_habit": _user_habit_mock,
    "home_event": _home_event_mock,
}


async def _run_one(query: DbQuery) -> DbQueryResultItem:
    spec = TABLE_SPECS.get(query.table)
    if spec is None:
        return DbQueryResultItem(
            table=query.table,
            count=0,
            items=[],
            error=DbQueryError(code="INVALID_FILTER", message=f"알 수 없는 테이블입니다: {query.table}", field="table"),
        )

    if spec.required_any and not (spec.required_any & query.filter.keys()):
        required = "|".join(sorted(spec.required_any))
        return DbQueryResultItem(
            table=query.table,
            count=0,
            items=[],
            error=DbQueryError(code="INVALID_FILTER", message=f"{required} 중 최소 1개는 필수입니다.", field=required),
        )

    disallowed = set(query.filter.keys()) - spec.allowed - {"id"}
    if disallowed:
        bad = sorted(disallowed)[0]
        return DbQueryResultItem(
            table=query.table,
            count=0,
            items=[],
            error=DbQueryError(code="INVALID_FILTER", message=f"허용되지 않은 필터입니다: {bad}", field=bad),
        )

    limit = max(1, min(query.limit, MAX_LIMIT))
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        filter_aware = _FILTER_AWARE_MOCK_GENERATORS.get(query.table)
        generator = _MOCK_GENERATORS.get(query.table)
        if filter_aware is not None:
            items = filter_aware(query.filter.get("userId"), query.filter)
        elif generator is not None:
            items = generator(query.filter.get("userId"))
        else:
            items = []
    else:
        response = await client.post("/db/query", json={"queries": [query.model_dump()]})
        result = response.get("results", [{}])[0]
        backend_error = result.get("error")
        if backend_error is not None:
            return DbQueryResultItem(table=query.table, count=0, items=[], error=DbQueryError(**backend_error))
        items = result.get("items", [])

    items = items[:limit]
    if query.order == "desc":
        items = list(reversed(items))
    return DbQueryResultItem(table=query.table, count=len(items), items=items)


async def query_db(queries: list[DbQuery]) -> list[DbQueryResultItem]:
    return [await _run_one(q) for q in queries[:MAX_QUERIES]]
