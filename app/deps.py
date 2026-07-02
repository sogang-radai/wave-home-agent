from __future__ import annotations

import secrets

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import ApiError
from app.models import Account, BrowserSession
from app.timeutil import utcnow

SESSION_COOKIE_NAME = "sid"


def _first_account(db: Session) -> Account | None:
    return db.query(Account).order_by(Account.id).first()


def get_or_create_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> BrowserSession:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    session_row = db.get(BrowserSession, sid) if sid else None

    if session_row is not None and db.get(Account, session_row.active_account_id) is not None:
        return session_row

    account = _first_account(db)
    if account is None:
        raise ApiError(409, "ACTIVE_ACCOUNT_REQUIRED", "활성 구성원을 먼저 선택해주세요.")

    if session_row is None:
        sid = secrets.token_hex(32)
        session_row = BrowserSession(sid=sid, active_account_id=account.id, updated_at=utcnow())
        db.add(session_row)
    else:
        session_row.active_account_id = account.id
        session_row.updated_at = utcnow()

    db.commit()
    db.refresh(session_row)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_row.sid,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return session_row


def get_active_account(
    session_row: BrowserSession = Depends(get_or_create_session),
    db: Session = Depends(get_db),
) -> Account:
    account = db.get(Account, session_row.active_account_id)
    if account is None:
        raise ApiError(409, "ACTIVE_ACCOUNT_REQUIRED", "활성 구성원을 먼저 선택해주세요.")
    return account
