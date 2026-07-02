from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import SessionLocal, create_db_and_tables
from app.errors import register_error_handlers
from app.routers import accounts, chat, session
from app.seed import seed_initial_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Wave Home API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(session.router)
api_v1.include_router(accounts.router)
api_v1.include_router(chat.router)
app.include_router(api_v1)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
