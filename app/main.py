from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import create_db_and_tables
from app.routers import items


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Wave Home API", lifespan=lifespan)

app.include_router(items.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
