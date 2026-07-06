"""Mock implementation of docs/api.md §2.6 POST /internal/v1/rag/search."""

from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.clients.core import CoreApiClient
from app.config import get_settings


RagCollection = Literal["sleep_report", "sleep_stat", "power_report"]


class RagTarget(BaseModel):
    collection: RagCollection
    userId: Optional[int] = None
    deviceId: Optional[int] = None
    period: Optional[str] = None
    from_: Optional[str] = None
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
    "sleep_stat": [],
    "power_report": [],
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
        "targets": [target.model_dump(exclude_none=True) for target in targets],
    }
    response = await client.post("/rag/search", json=payload)
    return [RagResult.model_validate(r) for r in response.get("results", [])]
