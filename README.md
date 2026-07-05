# WaveHome Agent Server

WaveHome의 에이전트 서버입니다.

프론트엔드와 직접 연동하는 일반 백엔드 서버가 아니라, C++ 서버가 호출하는 AI 에이전트 서버로 동작합니다. 사용자의 수면, 자세, 카메라 기반 관측 데이터, 일정, 가전 상태 등은 C++ 서버가 관리하며, 이 서버는 C++ 서버가 제공하는 API를 통해 필요한 데이터만 간접 조회하고 액션 요청을 전달합니다.

## 서버 역할

이 서버의 책임은 LangGraph 기반 에이전트 플로우를 실행해 채팅 응답, 건강 인사이트, 리포트, 권장 액션, 가전 제어 의도를 생성하는 것입니다.

### 1. 채팅

사용자와의 자연어 대화를 처리합니다.

채팅에서는 C++ 서버 API를 통해 수집 및 저장된 데이터를 조회한 뒤, 다음과 같은 응답을 생성합니다.

- 수면 데이터 기반 건강 상담
- 자세 데이터 기반 피드백
- 카메라 및 센서 관측 데이터 기반 생활 인사이트
- 사용자의 현재 상태와 최근 이력에 맞춘 권장 행동
- 일정 변경 요청 해석 및 실행 요청
- 가전 제어 요청 해석 및 실행 요청

예시 요청:

```text
어젯밤 수면 어땠어?
요즘 자세가 안 좋은 편이야?
밤 11시에 불 소등해줘.
에어컨 온도 조금 낮춰줘.
오늘 밤 운동 일정을 내일로 옮겨줘.
```

가전 제어와 일정 변경은 이 서버가 직접 DB를 수정하지 않고, LangGraph 플로우에서 의도를 파악한 뒤 C++ 서버의 API 또는 도구 호출로 전달합니다.

### 2. 인사이트 리포트

앱 화면에 표시할 건강 인사이트 리포트와 권장 액션을 생성합니다.

대상 리포트:

- 이번 주 수면 리포트
- 어젯밤 수면 리포트
- 이번 주 자세 리포트
- 오늘의 자세 리포트

각 리포트는 C++ 서버 API에서 받은 원천 데이터 또는 집계 데이터를 바탕으로 생성합니다. 결과에는 요약, 주요 변화, 위험 신호, 개선 포인트, 권장 액션이 포함될 수 있습니다.

## 아키텍처 원칙

### LangGraph 기반 에이전트

이 서버는 LangGraph를 중심으로 구현합니다.

예상 그래프 구성:

- 사용자 요청 분류
- 필요한 컨텍스트 결정
- C++ 서버 API를 통한 데이터 조회
- 건강 상담, 리포트 생성, 일정 관리, 가전 제어 등 작업별 노드 실행
- 도구 호출 결과 검증
- 최종 응답 생성

초기 구현은 단순한 그래프에서 시작하되, 기능이 늘어날수록 노드, 조건 분기, 상태 관리, 도구 호출을 명확히 분리합니다.

### DB 직접 접근 금지

WaveHome 전체 시스템은 SQLite를 사용할 수 있지만, 이 에이전트 서버는 SQLite DB에 직접 접근하지 않습니다.

SQLite는 동시 접근 시 lock 문제가 생길 수 있으므로 DB 접근 책임은 C++ 서버에 둡니다. 에이전트 서버는 아래 원칙을 따릅니다.

- SQLite 파일을 직접 열지 않는다.
- ORM 또는 SQL로 WaveHome DB를 직접 조회하지 않는다.
- 채팅, 수면, 자세, 일정, 기기 상태 데이터는 C++ 서버 API로 조회한다.
- 일정 변경, 가전 제어 등 상태 변경도 C++ 서버 API로 요청한다.
- 에이전트 실행에 필요한 일시적 상태는 LangGraph state 또는 별도 런타임 저장소에서 관리한다.

## 시스템 구성

```text
Frontend
   |
   v
C++ Server
   |
   |  HTTP/gRPC/tool API
   v
WaveHome Agent Server
   |
   v
LLM / LangGraph tools
```

데이터 소유권:

```text
C++ Server        : SQLite 접근, 사용자 데이터, 센서 데이터, 일정, 기기 상태, 가전 제어 실행
Agent Server      : 의도 해석, 상담, 리포트 생성, 권장 액션 생성, 도구 호출 계획
Frontend          : 화면 표시, 사용자 입력
```

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

## 환경 변수

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_MS=20000

WAVEHOME_CORE_API_BASE_URL=http://127.0.0.1:9000
WAVEHOME_CORE_API_TIMEOUT_MS=5000
WAVEHOME_CORE_API_MOCK=true
```

`WAVEHOME_CORE_API_MOCK=true`이면 C++ 서버가 아직 준비되지 않아도 mock context로 LangGraph 플로우를 실행할 수 있습니다. C++ 서버 API 연동이 준비되면 이 값을 `false`로 바꾸고 `app/clients/core.py`의 엔드포인트를 실제 스펙에 맞추면 됩니다.

## 프로젝트 구조

```text
app/
  graph/         # Supervisor/Chat/Report/Action/Health LangGraph 정의
  agents/        # Domain agent (Sleep/Posture/Observation/Lifestyle/Schedule/Device/Report)
  tools/         # C++ 서버 API를 감싸는 도메인별 Tool 함수
  state/         # 공유 AgentState
  models/        # Insight/HealthSummary/ActionPlan 등 내부 pydantic 모델
  services/      # LLM 클라이언트, 프롬프트 로더, Insight Synthesizer
  prompts/       # 도메인별 LLM 프롬프트 템플릿
  clients/       # C++ 서버 API 공용 transport (get/post, 재시도)
  routers/       # Agent API endpoint
  schemas/       # Request/response schema
  config.py      # 환경 변수 설정
  main.py        # FastAPI entrypoint
docs/
  agent_architecture.md
  design.md
  interface.md
  db.md
  schema.sql
```

## API 구현

```http
POST /api/v1/agent/chat
POST /api/v1/agent/reports/sleep/weekly
POST /api/v1/agent/reports/sleep/nightly
POST /api/v1/agent/reports/posture/weekly
POST /api/v1/agent/reports/posture/daily
POST /api/v1/agent/actions/recommend
```

세부 요청/응답 스펙은 C++ 서버와의 연동 방식이 확정된 뒤 문서화합니다.

## TODO
- C++ 서버 API가 준비되면 `app/tools/*_api.py`의 mock 분기를 실제 엔드포인트로 교체
- 카메라/센서 관측 데이터 API가 생기면 `app/tools/observation_api.py`를 실제 연동으로 교체
- Human-in-the-Loop, LangGraph Checkpoint/Memory, LangSmith 추적 등 `docs/agent_architecture.md` §15의 향후 발전 방향 검토
