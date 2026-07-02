from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_or_create_session
from app.errors import ApiError
from app.models import Account, BrowserSession
from app.timeutil import utcnow

router = APIRouter(tags=["session"])


class AccountOut(BaseModel):
    id: str
    name: str


class SessionOut(BaseModel):
    activeAccount: AccountOut


class SwitchActiveAccountIn(BaseModel):
    accountId: str


@router.get("/session", response_model=SessionOut)
def get_session(
    session_row: BrowserSession = Depends(get_or_create_session),
    db: Session = Depends(get_db),
) -> SessionOut:
    account = db.get(Account, session_row.active_account_id)
    return SessionOut(activeAccount=AccountOut(id=account.id, name=account.name))


@router.patch("/session/active-account", response_model=SessionOut)
def switch_active_account(
    body: SwitchActiveAccountIn,
    session_row: BrowserSession = Depends(get_or_create_session),
    db: Session = Depends(get_db),
) -> SessionOut:
    account = db.get(Account, body.accountId)
    if account is None:
        raise ApiError(404, "NOT_FOUND", "구성원을 찾을 수 없습니다.")

    session_row.active_account_id = account.id
    session_row.updated_at = utcnow()
    db.commit()

    return SessionOut(activeAccount=AccountOut(id=account.id, name=account.name))
