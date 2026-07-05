from fastapi import FastAPI

from app.config import get_settings
from app.routers import agent


settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(agent.router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "wavehome-agent"}
