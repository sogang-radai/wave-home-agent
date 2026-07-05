from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import FCM_VAPID_KEY
from app.database import get_db
from app.deps import get_active_account
from app.ids import new_id
from app.models import Account, PushSubscription
from app.push_service import notify_account_with_delivery
from app.timeutil import utcnow

router = APIRouter(prefix="/push", tags=["push"])


class PushSubscriptionIn(BaseModel):
    token: str


class UnsubscribeIn(BaseModel):
    token: str


class PushTestIn(BaseModel):
    message: str = "테스트 알림입니다."
    icon: Optional[str] = None
    image: Optional[str] = None


@router.get("/public-key")
def get_public_key() -> dict[str, str]:
    """firebase getToken(messaging, { vapidKey })에 그대로 넘길 Web Push 인증서 공개키."""
    return {"publicKey": FCM_VAPID_KEY}


@router.post("/subscribe", status_code=201)
def subscribe(
    body: PushSubscriptionIn,
    request: Request,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.token == body.token))
    user_agent = request.headers.get("user-agent", "")[:255]

    if existing is not None:
        existing.account_id = account.id
        existing.user_agent = user_agent
    else:
        db.add(
            PushSubscription(
                id=new_id("psh"),
                account_id=account.id,
                token=body.token,
                user_agent=user_agent,
                created_at=utcnow(),
            )
        )

    db.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn, db: Session = Depends(get_db)) -> dict[str, bool]:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.token == body.token))
    if existing is not None:
        db.delete(existing)
        db.commit()
    return {"ok": True}


@router.post("/test")
def send_test_push(
    body: PushTestIn,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """알림 패널 + FCM 발송을 한 번에 검증하기 위한 개발용 엔드포인트."""
    notification, delivery = notify_account_with_delivery(
        db, account.id, "timer", body.message, icon=body.icon, image=body.image
    )
    return {
        "ok": True,
        "notificationId": notification.id,
        "subscriptionCount": len(delivery),
        "sentCount": sum(1 for item in delivery if item["status"] == "sent"),
        "delivery": [
            {
                "tokenPrefix": item["token"][:12],
                "tokenLength": len(item["token"]),
                "status": item["status"],
                "error": item["error"],
            }
            for item in delivery
        ],
    }
