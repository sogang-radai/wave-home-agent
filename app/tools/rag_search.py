"""Mock implementation of docs/api.md §2.6 POST /internal/v1/rag/search."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.clients.core import CoreApiClient
from app.config import get_settings


RagCollection = Literal["sleep_report", "sleep_stat", "power_report"]


class RagTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    collection: RagCollection
    userId: Optional[int] = None
    deviceId: Optional[int] = None
    period: Optional[str] = None
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
