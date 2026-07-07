from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.errors import AgentApiError
from app.schemas.jobs import JobRef
from app.schemas.power_analysis import PowerReportRequest
from app.services.jobs import job_store
from app.services.power_analysis import REPORT_KIND, create_report_job


router = APIRouter(prefix="/power/v1", tags=["power-analysis"])


@router.post("/reports", response_model=JobRef, status_code=202)
async def create_report(body: PowerReportRequest) -> JobRef:
    return create_report_job(body)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = job_store.get(job_id, kinds={REPORT_KIND})
    if job is None:
        raise AgentApiError(404, "JOB_NOT_FOUND", "jobId 에 해당하는 작업이 없습니다.")

    payload = {"jobId": job.job_id, "status": job.status}
    if job.result is not None:
        payload["result"] = job.result
    if job.error is not None:
        payload["error"] = job.error
    return JSONResponse(content=payload)
