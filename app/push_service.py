from __future__ import annotations

import logging
from typing import Optional, TypedDict

from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.firebase_client import get_firebase_app
from app.ids import new_id
from app.models import Notification, PushSubscription
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

_NOTIFICATION_TITLES = {
    "sleep": "수면 알림",
    "posture": "자세 알림",
    "temperature": "온도 알림",
    "timer": "타이머 알림",
}


class PushSendResult(TypedDict):
    token: str
    status: str
    error: Optional[str]


def send_fcm_push(
    db: Session,
    subscription: PushSubscription,
    *,
    title: str,
    body: str,
    url: str = "/",
    icon: Optional[str] = None,
    image: Optional[str] = None,
) -> PushSendResult:
    """토큰 하나에 발송한다. 토큰이 만료/철회된 경우(UnregisteredError) DB에서 정리한다."""
    if get_firebase_app() is None:
        return {"token": subscription.token, "status": "firebase-disabled", "error": None}

    # WebpushFCMOptions.link은 https:// 절대 URL만 허용한다(로컬 개발용 http://localhost는 불가).
    # 실제 클릭 시 이동할 경로는 어차피 data.url로 서비스워커에 전달되므로, https가 아니면 생략한다.
    fcm_options = messaging.WebpushFCMOptions(link=url) if url.startswith("https://") else None

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body, image=image),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(title=title, body=body, icon=icon, image=image),
            fcm_options=fcm_options,
        ),
        data={"url": url},
        token=subscription.token,
    )

    try:
        message_id = messaging.send(message)
        logger.info("FCM push sent for token=%s message_id=%s", subscription.token[:12], message_id)
        return {"token": subscription.token, "status": "sent", "error": None}
    except messaging.UnregisteredError:
        db.delete(subscription)
        db.commit()
        return {"token": subscription.token, "status": "unregistered", "error": None}
    except firebase_exceptions.FirebaseError as exc:
        logger.warning("FCM push failed for token=%s: %s", subscription.token, exc)
        return {"token": subscription.token, "status": "error", "error": str(exc)}


def notify_account(
    db: Session,
    account_id: str,
    type_: str,
    message: str,
    url: str = "/",
    *,
    icon: Optional[str] = None,
    image: Optional[str] = None,
) -> Notification:
    """알림 센터(Notification row)에 저장하고, 동시에 해당 계정의 모든 FCM 토큰으로 푸시를 보낸다."""
    notification = Notification(
        id=new_id("ntf"),
        account_id=account_id,
        type=type_,
        message=message,
        created_at=utcnow(),
        read=False,
    )
    db.add(notification)
    db.commit()

    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.account_id == account_id)
    ).all()
    title = _NOTIFICATION_TITLES.get(type_, "WaveHome")
    for subscription in subscriptions:
        send_fcm_push(db, subscription, title=title, body=message, url=url, icon=icon, image=image)

    return notification


def notify_account_with_delivery(
    db: Session,
    account_id: str,
    type_: str,
    message: str,
    url: str = "/",
    *,
    icon: Optional[str] = None,
    image: Optional[str] = None,
) -> tuple[Notification, list[PushSendResult]]:
    """개발/진단용: 알림 저장과 FCM 발송 결과를 함께 반환한다."""
    notification = Notification(
        id=new_id("ntf"),
        account_id=account_id,
        type=type_,
        message=message,
        created_at=utcnow(),
        read=False,
    )
    db.add(notification)
    db.commit()

    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.account_id == account_id)
    ).all()
    title = _NOTIFICATION_TITLES.get(type_, "WaveHome")
    results = [
        send_fcm_push(db, subscription, title=title, body=message, url=url, icon=icon, image=image)
        for subscription in subscriptions
    ]

    return notification, results
