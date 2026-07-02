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

## 기본 API

현재는 예시 리소스로 `items` CRUD가 포함되어 있습니다.

```bash
curl -X POST http://127.0.0.1:8000/items \
  -H "Content-Type: application/json" \
  -d '{"title":"첫 번째 아이템","description":"SQLite 저장 테스트"}'
```

## AI Agent 구현

초기에는 FastAPI와 Gemini API를 직접 연동하여 채팅 및 AI 리포트 생성 기능을 구현합니다. 이 과정에서 필요한 사용자 데이터와 기록은 DB에서 조회하며, 이후 로직이 복잡해지면 LangGraph를 도입해 여러 에이전트 호출, 조건 분기, 상태 관리를 체계적으로 확장할 계획입니다.
