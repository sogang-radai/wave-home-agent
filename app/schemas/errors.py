from typing import Any, Literal, Optional

from pydantic import BaseModel


ErrorCode = Literal[
    "INVALID_REQUEST",
    "NOT_FOUND",
    "CONFLICT",
    "UNSUPPORTED_INTENT",
    "CORE_API_UNAVAILABLE",
    "LLM_PROVIDER_ERROR",
    "CORE_API_TIMEOUT",
    "MODEL_NOT_FOUND",
    "LLM_TIMEOUT",
    # docs/api.md §1.4 (Sleep/Power Analysis API, job pattern)
    "INVALID_WINDOW",
    "NO_SLEEP_DATA",
    "INVALID_WEEK_START",
    "JOB_ALREADY_RUNNING",
    "JOB_NOT_FOUND",
    "GENERATION_FAILED",
    "GENERATION_TIMEOUT",
]


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    field: Optional[str] = None
    detail: Optional[dict[str, Any]] = None
    jobId: Optional[str] = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
