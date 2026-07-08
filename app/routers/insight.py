from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.insight import InsightGenerationRequest
from app.schemas.jobs import JobRef
from app.services.insight import INSIGHT_KIND, create_insight_job
from app.services.job_common import get_job_or_404, job_response


router = APIRouter(prefix="/insight/v1", tags=["insight-generation"])


@router.post("/insights", response_model=JobRef, status_code=202)
async def create_insight(body: InsightGenerationRequest) -> JobRef:
    return create_insight_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    return job_response(get_job_or_404(job_id, kinds={INSIGHT_KIND}))
