from fastapi import APIRouter

from app.errors import AgentApiError
from app.graph.report_turn_graph import build
from app.schemas.report_turn import ReportDomain, ReportPeriod, ReportTurnRequest, ReportTurnResponse


router = APIRouter(tags=["reports"])

_report_graph = build()


@router.post("/reports/v1/{domain}/{period}", response_model=ReportTurnResponse)
async def generate_report(domain: ReportDomain, period: ReportPeriod, body: ReportTurnRequest) -> ReportTurnResponse:
    if not body.metrics:
        raise AgentApiError(400, "INVALID_REQUEST", "metrics 가 비어 있습니다.", field="metrics")

    result = await _report_graph.ainvoke(
        {
            "user_id": body.userId,
            "domain": domain,
            "period": period,
            "period_start": body.periodStart,
            "metrics": body.metrics,
            "raw": body.raw,
            "rounds": 0,
        }
    )
    content = result["content"]
    return ReportTurnResponse(
        domain=domain,
        period=period,
        periodStart=body.periodStart,
        summary=content["summary"],
        highlights=content["highlights"],
        recommendations=content["recommendations"],
        sources=result.get("sources", ["core-api"]),
    )
