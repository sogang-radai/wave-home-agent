from __future__ import annotations

import logging
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials

from app.config import FIREBASE_CREDENTIALS_PATH

logger = logging.getLogger(__name__)

_app: Optional[firebase_admin.App] = None
_warned = False


def get_firebase_app() -> Optional[firebase_admin.App]:
    """서비스 계정 파일이 없으면 None을 반환한다 — Firebase 프로젝트 설정 전에도 서버가 죽지 않도록."""
    global _app, _warned

    if _app is not None:
        return _app

    if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
        if not _warned:
            logger.warning(
                "Firebase 서비스 계정 파일을 찾을 수 없습니다(%s) — 웹 푸시 발송이 비활성화됩니다. "
                "FIREBASE_CREDENTIALS_PATH를 .env에 설정해주세요.",
                FIREBASE_CREDENTIALS_PATH,
            )
            _warned = True
        return None

    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    _app = firebase_admin.initialize_app(cred)
    return _app
