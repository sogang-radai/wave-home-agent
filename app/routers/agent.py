from fastapi import APIRouter

from app.graph.supervisor_graph import run_agent
from app.schemas.agent import (
    ActionRecommendationRequest,
    ActionRecommendationResponse,
    ChatRequest,
    ChatResponse,
    ReportRequest,
    ReportResponse,
)


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    result = await run_agent(
        task="chat",
        account_id=request.account_id,
        user_message=request.message,
        metadata=request.metadata,
    )
    return ChatResponse(**result)


@router.post("/reports/sleep/weekly", response_model=ReportResponse)
async def weekly_sleep_report(request: ReportRequest) -> ReportResponse:
    result = await run_agent(
        task="weekly_sleep_report",
        account_id=request.account_id,
        metadata=request.metadata,
    )
    return ReportResponse(**result)


@router.post("/reports/sleep/nightly", response_model=ReportResponse)
async def nightly_sleep_report(request: ReportRequest) -> ReportResponse:
    result = await run_agent(
        task="nightly_sleep_report",
        account_id=request.account_id,
        metadata=request.metadata,
    )
    return ReportResponse(**result)


@router.post("/reports/posture/weekly", response_model=ReportResponse)
async def weekly_posture_report(request: ReportRequest) -> ReportResponse:
    result = await run_agent(
        task="weekly_posture_report",
        account_id=request.account_id,
        metadata=request.metadata,
    )
    return ReportResponse(**result)


@router.post("/reports/posture/daily", response_model=ReportResponse)
async def daily_posture_report(request: ReportRequest) -> ReportResponse:
    result = await run_agent(
        task="daily_posture_report",
        account_id=request.account_id,
        metadata=request.metadata,
    )
    return ReportResponse(**result)


@router.post("/actions/recommend", response_model=ActionRecommendationResponse)
async def recommend_actions(
    request: ActionRecommendationRequest,
) -> ActionRecommendationResponse:
    result = await run_agent(
        task="recommend_actions",
        account_id=request.account_id,
        user_message=request.goal,
        metadata=request.metadata,
    )
    return ActionRecommendationResponse(**result)
