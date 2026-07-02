from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import ApiError
from app.ids import new_id
from app.models import Account

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountOut(BaseModel):
    id: str
    name: str


class CreateAccountIn(BaseModel):
    name: str


class UpdateAccountIn(BaseModel):
    name: str


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[AccountOut]:
    accounts = db.scalars(select(Account).order_by(Account.id)).all()
    return [AccountOut(id=a.id, name=a.name) for a in accounts]


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: CreateAccountIn, db: Session = Depends(get_db)) -> AccountOut:
    name = body.name.strip()
    if not name:
        raise ApiError(400, "INVALID_NAME", "이름을 입력해주세요.", field="name")

    account = Account(id=new_id("acc"), name=name)
    db.add(account)
    db.commit()
    return AccountOut(id=account.id, name=account.name)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: str, body: UpdateAccountIn, db: Session = Depends(get_db)) -> AccountOut:
    account = db.get(Account, account_id)
    if account is None:
        raise ApiError(404, "NOT_FOUND", "구성원을 찾을 수 없습니다.")

    name = body.name.strip()
    if not name:
        raise ApiError(400, "INVALID_NAME", "이름을 입력해주세요.", field="name")

    account.name = name
    db.commit()
    return AccountOut(id=account.id, name=account.name)


@router.delete("/{account_id}")
def delete_account(account_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    account = db.get(Account, account_id)
    if account is None:
        raise ApiError(404, "NOT_FOUND", "구성원을 찾을 수 없습니다.")

    db.delete(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            409, "ACCOUNT_IN_USE", "이 구성원과 연결된 데이터가 있어 삭제할 수 없습니다."
        ) from exc

    return {"id": account_id}
