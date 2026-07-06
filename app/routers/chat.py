from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.graph.chat_runtime import run_turn_sync, stream_turn
from app.schemas.chat import ChatTurnRequest, ChatTurnResponse


router = APIRouter(tags=["chat"])


@router.post("/chat/v1/turns", response_model=ChatTurnResponse)
async def turns(body: ChatTurnRequest, request: Request):
    if body.stream:
        return StreamingResponse(
            stream_turn(body, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    return await run_turn_sync(body)
