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


def _routine_task_mock(user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 501,
            "userId": user_id,
            "title": "운동",
            "category": "exercise",
            "dayOfWeek": "mon",
            "startMinute": 1260,
            "endMinute": 1290,
            "done": False,
        }
    ]


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
    "routine_task": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "category", "dayOfWeek", "done", "createdBy"},
    ),
    "notification": _TableSpec(required_any={"userId"}, allowed={"id", "userId", "type", "read", "from", "to"}),
    "chat_history": _TableSpec(required_any={"userId"}, allowed={"id", "userId", "from", "to"}),
    "insight": _TableSpec(
        required_any={"userId"},
        allowed={"id", "userId", "domain", "period", "approved", "from", "to"},
    ),
}

_MOCK_GENERATORS = {
    "sleep_session": _sleep_session_mock,
    "sleep_stat": _sleep_stat_mock,
    "sleep_report": _sleep_report_mock,
    "routine_task": _routine_task_mock,
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
    generator = _MOCK_GENERATORS.get(query.table)
    if client.is_mock:
        items = generator(query.filter.get("userId")) if generator else []
    else:
        response = await client.post("/db/query", json={"queries": [query.model_dump()]})
        items = response.get("results", [{}])[0].get("items", [])

    items = items[:limit]
    if query.order == "desc":
        items = list(reversed(items))
    return DbQueryResultItem(table=query.table, count=len(items), items=items)


async def query_db(queries: list[DbQuery]) -> list[DbQueryResultItem]:
    return [await _run_one(q) for q in queries[:MAX_QUERIES]]
