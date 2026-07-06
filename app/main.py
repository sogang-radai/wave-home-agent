from fastapi import FastAPI

from app.config import get_settings
from app.errors import AgentApiError, agent_api_error_handler
from app.routers import chat, llm, reports_turn


settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_exception_handler(AgentApiError, agent_api_error_handler)
app.include_router(chat.router)  # docs/api.md §1.1
app.include_router(reports_turn.router)  # docs/api.md §1.2
app.include_router(llm.router)  # docs/api.md §1.3


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "wavehome-agent"}
