from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "20000"))

# Firebase Console > 프로젝트 설정 > 클라우드 메시징 > 웹 구성 > 웹 푸시 인증서 키 쌍.
# 프론트의 getToken(messaging, { vapidKey })에 그대로 전달되는 "공개" 값이라 노출돼도 안전하다.
FCM_VAPID_KEY = os.getenv("FCM_VAPID_KEY", "")

# Firebase Console > 프로젝트 설정 > 서비스 계정 > 새 비공개 키 생성으로 받은 JSON 파일 경로.
# firebase-admin이 이 파일로 서버 자격 증명을 초기화한다. 저장소에 커밋하지 말 것(.gitignore 처리됨).
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "./firebase-service-account.json")
