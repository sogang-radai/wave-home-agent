# WaveHome Backend

FastAPI와 SQLite를 사용하는 백엔드 서버입니다.

## 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

서버가 실행되면 아래 주소를 사용할 수 있습니다.

- API: http://127.0.0.1:8000
- Swagger 문서: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Database

서버를 처음 실행하면 프로젝트 루트에 `wave_home.db` 파일이 자동으로 생성됩니다.
초기 개발 단계에서는 SQLite를 사용하여 채팅 기록, 사용자 데이터, AI 리포트 결과를 저장합니다. 이후 사용자 수 증가, 동시 요청 처리, 배포 환경 확장 등이 필요해질 경우 PostgreSQL 등 운영용 데이터베이스로 전환할 수도 있습니다.

## AI Agent 구현

초기에는 FastAPI와 Gemini API를 직접 연동하여 채팅 및 AI 리포트 생성 기능을 구현합니다. 이 과정에서 필요한 사용자 데이터와 기록은 DB에서 조회하며, 이후 로직이 복잡해지면 LangGraph를 도입해 여러 에이전트 호출, 조건 분기, 상태 관리를 체계적으로 확장할 계획입니다.


## 구현완료된 API endpoint(도메인별)

모든 엔드포인트의 base path는 `/api/v1`이다. 세부 요청/응답 스펙은 프론트 레포의 `docs/api/settings.md`(세션·계정), `docs/api/chat.md`(채팅)를 따른다.

### 세션 (Session)

브라우저별 `sid` 쿠키로 활성 구성원을 관리한다. 쿠키가 없거나 세션이 유효하지 않으면
서버가 첫 번째 계정을 자동으로 선택하고 쿠키를 새로 내려준다.

```http
GET   /api/v1/session                    # 활성 구성원 조회 (없으면 자동 부트스트랩)
PATCH /api/v1/session/active-account     # 활성 구성원 전환
```

### 계정 (Accounts)

```http
GET    /api/v1/accounts                  # 전체 구성원 목록
POST   /api/v1/accounts                  # 구성원 추가
PATCH  /api/v1/accounts/{accountId}      # 구성원 이름 변경
DELETE /api/v1/accounts/{accountId}      # 구성원 삭제
```

### 채팅 (Chat)

활성 구성원(`activeAccount`) 기준으로 동작하며, 답변 생성 시 Gemini API를 호출한다.
호출 시점에 해당 구성원의 최근 수면/자세 데이터를 컨텍스트로 함께 넣는다.

```http
GET    /api/v1/chat/conversations                       # 대화 목록 (summary)
POST   /api/v1/chat/conversations                       # 대화 생성 (빈 대화 또는 첫 메시지 포함)
GET    /api/v1/chat/conversations/{conversationId}      # 대화 상세 + 메시지 전체
PATCH  /api/v1/chat/conversations/{conversationId}      # 대화 제목 변경
DELETE /api/v1/chat/conversations/{conversationId}      # 대화 삭제

POST   /api/v1/chat/conversations/{conversationId}/messages   # 메시지 전송 + AI 답변 생성

GET    /api/v1/chat/suggestions          # 추천 질문 칩 (웰컴 카드 / 팝업 / 인사이트 위젯 공용)
POST   /api/v1/chat/insight-queries      # 대화 이력 없는 1회성 인사이트 질의
```

### 기타

```http
GET /health   # 헬스 체크
```

### 아직 구현되지 않은 도메인

대시보드, 방/기기, 수면·자세 트래킹, 주간 계획, 전력 모니터링, 설정(수면/일반/알림), 가전 제어는 아직 백엔드에 없다. 프론트는 해당 도메인을 계속 mock API로 사용 중이다.
