"""Mock implementation of docs/api.md §2.6 POST /internal/v1/rag/search."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.clients.core import CoreApiClient
from app.config import get_settings


RagCollection = Literal[
    "sleep_stat",
    "sleep_report",
    "power_report",
    "posture_report",
    "weekly_plan_report",
    "insight_dashboard",
    "insight_weekly_plan",
    "insight_sleep",
    "insight_posture",
    "insight_power",
]


class RagTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    collection: RagCollection
    userId: Optional[int] = None
    deviceId: Optional[int] = None
    period: Optional[str] = None
    date: Optional[str] = None  # insight_* 컬렉션의 필터 축 (rag-api.md)
    from_: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    topK: int = 3


class RagHit(BaseModel):
    refId: int
    score: float
    text: str


class RagResult(BaseModel):
    collection: RagCollection
    hits: list[RagHit]


_MOCK_HITS: dict[RagCollection, list[RagHit]] = {
    "sleep_report": [
        RagHit(refId=812, score=0.83, text="7월 1일 밤 수면은 총 5시간 36분으로 목표보다 30분 부족했습니다."),
    ],
    "sleep_stat": [
        RagHit(
            refId=91201,
            score=0.79,
            text="7월 6일 새벽 3시~3시 30분 구간은 깊은 수면 비율이 낮고 평소보다 심박수가 높아 수면의 질이 다소 떨어졌습니다.",
        ),
        RagHit(
            refId=91198,
            score=0.71,
            text="최근 며칠간 새벽 2시~4시 사이에 뒤척임이 잦아지는 패턴이 반복되고 있습니다.",
        ),
    ],
    "power_report": [
        RagHit(refId=305, score=0.75, text="이번 주 거실 에어컨 전력 사용량이 지난주 대비 15% 증가했습니다."),
    ],
    "posture_report": [
        RagHit(refId=901, score=0.70, text="이번 주 평균 앉은 자세 점수는 72점으로 전주 대비 소폭 개선되었습니다."),
    ],
    "weekly_plan_report": [
        RagHit(refId=1201, score=0.77, text="이번 주는 수면 목표를 4/7일 달성했고, 자세 교정 루틴은 절반가량 수행했습니다."),
    ],
    "insight_dashboard": [
        RagHit(refId=2001, score=0.68, text="어젯밤 수면 효율이 평소보다 낮았어요 · 오늘은 일찍 잠자리에 들어보세요."),
    ],
    "insight_weekly_plan": [
        RagHit(refId=2101, score=0.74, text="이번 주 목표 달성률 · 수면 루틴을 3일 이상 놓쳤어요, 취침 알람을 설정해볼까요?"),
    ],
    "insight_sleep": [
        RagHit(refId=2201, score=0.72, text="수면 효율 저하 · 최근 3일간 새벽 뒤척임이 늘었습니다."),
    ],
    "insight_posture": [
        RagHit(refId=2301, score=0.66, text="장시간 앉은 자세 · 1시간 이상 연속 착석이 반복되고 있습니다."),
    ],
    "insight_power": [
        RagHit(refId=2401, score=0.69, text="대기전력 절감 팁 · 야간 대기전력이 지난주보다 늘었습니다."),
    ],
}


async def rag_search(query: str, targets: list[RagTarget]) -> list[RagResult]:
    client = CoreApiClient(base_url=get_settings().wavehome_agent_internal_base_url)
    if client.is_mock:
        return [
            RagResult(collection=target.collection, hits=_MOCK_HITS.get(target.collection, [])[: target.topK])
            for target in targets
        ]

    payload: dict[str, Any] = {
        "query": query,
        "targets": [target.model_dump(exclude_none=True, by_alias=True) for target in targets],
    }
    response = await client.post("/rag/search", json=payload)
    return [RagResult.model_validate(r) for r in response.get("results", [])]
