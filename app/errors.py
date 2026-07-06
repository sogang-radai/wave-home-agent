from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.errors import ErrorCode, ErrorDetail, ErrorEnvelope


class AgentApiError(Exception):
    """Raised by routers to produce the api.md §4 error envelope."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        field: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field
        self.detail = detail

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorDetail(code=self.code, message=self.message, field=self.field, detail=self.detail)
        )


async def agent_api_error_handler(request: Request, exc: AgentApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope().model_dump(exclude_none=True))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Maps FastAPI/pydantic's default 422 body onto the api.md §4 envelope
    (400 INVALID_REQUEST), e.g. api.md §1.1's documented `messages` example."""
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"][1:]) or None  # loc[0] is always "body"
    envelope = ErrorEnvelope(error=ErrorDetail(code="INVALID_REQUEST", message=first["msg"], field=field))
    return JSONResponse(status_code=400, content=envelope.model_dump(exclude_none=True))
