"""POST /insight/v1/appliance-banner 요청/응답 스키마.

가전 제어 배너는 실시간으로 바뀌는 조명 on/off 상태를 자연어 한 문장으로 요약한다.
다른 배너들과 마찬가지로 gather 단계가 없다 — 백엔드(iot_controller.cpp)가 이미 계산한
방별 조명 on/off 카운트를 인라인으로 넘겨주고, LLM은 그걸 자연스러운 문장으로 다듬는
작업만 한다. 응답 스키마는 app/schemas/banner.py 의 GeneratedBanner 를 그대로 재사용해서
C++ 쪽 runBannerJobSync/AgentBannerJobResult 폴링 로직을 그대로 재사용할 수 있게 한다
(headline 은 프런트가 이미 정적 "가전 제어" 제목을 쓰므로 실제로는 body 만 쓰인다).
"""

from pydantic import BaseModel, Field

from app.schemas.banner import GeneratedBanner


__all__ = ["ApplianceRoomState", "ApplianceBannerRequest", "GeneratedBanner"]


class ApplianceRoomState(BaseModel):
    room: str
    on: int
    total: int


class ApplianceBannerRequest(BaseModel):
    rooms: list[ApplianceRoomState] = Field(default_factory=list)
