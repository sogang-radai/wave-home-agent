from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_active_account
from app.models import Account, Notification
from app.timeutil import to_iso_kst

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    message: str
    createdAt: str
    read: bool


def _notification_out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        type=notification.type,
        message=notification.message,
        createdAt=to_iso_kst(notification.created_at),
        read=notification.read,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.account_id == account.id)
        .order_by(Notification.created_at.desc())
    ).all()
    return [_notification_out(n) for n in notifications]


@router.patch("/read-all", response_model=list[NotificationOut])
def mark_all_notifications_read(
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.account_id == account.id)
        .order_by(Notification.created_at.desc())
    ).all()
    for notification in notifications:
        notification.read = True
    db.commit()
    return [_notification_out(n) for n in notifications]
