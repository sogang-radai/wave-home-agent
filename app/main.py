import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.errors import AgentApiError, agent_api_error_handler, validation_error_handler
from app.routers import chat, goal_coaching, insight, llm, power_analysis, reports_turn, sleep_analysis, weekly_plan


# INFO-level app.* logs (job lifecycle in app/services/jobs.py, embedding calls in
# app/services/embeddings.py) are otherwise swallowed — Python's logging module only
# shows WARNING+ via its "handler of last resort" when no handler is configured.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_exception_handler(AgentApiError, agent_api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(chat.router)  # docs/api.md §1.1
app.include_router(reports_turn.router)  # docs/api.md §1.2
app.include_router(llm.router)  # docs/api.md §1.3
app.include_router(sleep_analysis.router)  # docs/api.md §1.4
app.include_router(power_analysis.router)  # docs/api.md §1.4
app.include_router(insight.router)  # agent-be/agent-api/insight-generation-api.md
app.include_router(weekly_plan.router)  # agent-be/agent-api/weekly-plan-analysis-api.md
app.include_router(goal_coaching.router)  # goal-based habit coaching (신규)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "wavehome-agent"}
