# WaveHome Agent Server

WaveHome의 에이전트 서버입니다.

프론트엔드와 직접 연동하는 일반 백엔드 서버가 아니라, C++ 서버가 호출하는 AI 에이전트 서버로 동작합니다. 사용자의 수면, 자세, 카메라 기반 관측 데이터, 일정, 가전 상태 등은 C++ 서버가 관리하며, 이 서버는 C++ 서버가 제공하는 API를 통해 필요한 데이터만 간접 조회하고 액션 요청을 전달합니다.

## 서버 역할

이 서버의 책임은 LangGraph 기반 에이전트 플로우를 실행해 채팅 응답, 건강 인사이트, 리포트, 권장 액션, 가전 제어 의도를 생성하는 것입니다.

> **API 계약 현황**: `docs/api.md`가 백엔드-에이전트 계약의 확정안입니다. 현재 서버는 두 API 표면을 동시에 제공합니다 — 초기 설계(`docs/agent_architecture.md`)를 따르는 레거시 `/api/v1/agent/*` 라우트(키워드 기반 라우팅, 비스트리밍)와, `docs/api.md`를 그대로 구현한 `/chat/v1/turns`·`/reports/v1/{domain}/{period}`(LLM이 직접 tool 호출 여부를 판단하는 ReAct 루프, SSE 스트리밍)입니다. 레거시 쪽은 당장 정리하지 않고 병행 운영 중이며, 자세한 API별 구현 여부는 아래 "API 구현" 절을 참고합니다.

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

각 리포트는 C++ 서버 API에서 받은 원천 데이터 또는 집계 데이터를 바탕으로 생성합니다. 결과에는 요약(핵심 지표를 한눈에 보도록 문장 형태로), 주요 변화(이전 대비 달라진 점), 위험 신호(주의가 필요한 징후), 개선 포인트, 권장 액션이 포함될 수 있습니다.

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

`langchain-google-genai>=3.1`(Gemini 3 tool-calling의 thought_signature 버그 수정 버전)이 **Python 3.10 이상**을 요구하므로, `.python-version`에 `3.12.10`을 고정해 두었습니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8501
```

서버가 실행되면 아래 주소를 사용할 수 있습니다(포트는 `docs/api.md`의 기본 경로 예시와 맞춘 8501).

- API: http://127.0.0.1:8501
- Swagger 문서: http://127.0.0.1:8501/docs
- Health check: http://127.0.0.1:8501/health

## 환경 변수

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_MS=20000

# 레거시 /api/v1/agent/* 라우트가 사용
WAVEHOME_CORE_API_BASE_URL=http://127.0.0.1:9000
WAVEHOME_CORE_API_TIMEOUT_MS=5000
WAVEHOME_CORE_API_MOCK=true

# docs/api.md §2 /internal/v1/* 아웃바운드 tool(db.query, devices, routine-tasks, rag.search)이 사용
WAVEHOME_AGENT_INTERNAL_BASE_URL=http://127.0.0.1:8500/internal/v1
```

`WAVEHOME_CORE_API_MOCK=true`이면 C++ 서버가 아직 준비되지 않아도 mock context로 LangGraph 플로우를 실행할 수 있습니다. C++ 서버 API 연동이 준비되면 이 값을 `false`로 바꾸고 `app/clients/core.py`의 엔드포인트를 실제 스펙에 맞추면 됩니다.

`docs/api.md` §2의 새 outbound tool(`app/tools/db_query.py`, `rag_search.py`, `devices_internal.py`, `routine_tasks_internal.py`)도 같은 `CoreApiClient.is_mock` 패턴을 쓰지만, 백엔드의 `/internal/v1/*`가 아직 없어 지금은 항상 mock 데이터를 반환합니다. 실제 백엔드가 준비되면 `WAVEHOME_AGENT_INTERNAL_BASE_URL`만 맞는 주소로 바꾸면 됩니다(코드 변경 불필요).

## 프로젝트 구조

```text
app/
  graph/
    supervisor_graph.py / chat_graph.py / report_graph.py / action_graph.py / health_graph.py
                       # 레거시: 키워드 기반 라우팅 + 고정 fan-out (docs/agent_architecture.md)
    tool_loop.py       # 신규: LLM이 tool 호출 여부를 스스로 판단하는 2노드 ReAct 루프(공용)
    turn_graph.py      # 신규: /chat/v1/turns용 tool_loop 인스턴스 + 시스템 프롬프트
    tools.py           # 신규: LangChain @tool 래퍼 (build_tools(user_id))
    chat_runtime.py    # 신규: SSE/비스트리밍 드라이버 (astream_events -> tool.start/tool.end/message.delta)
    report_turn_graph.py  # 신규: /reports/v1/{domain}/{period}용 그래프 (metrics/raw 인라인 소비)
  agents/          # 레거시: Domain agent (Sleep/Posture/Observation/Lifestyle/Schedule/Device/Report)
  tools/
    *_api.py                    # 레거시: 옛 /api/v1/agent/* 계약 기준 mock/실call
    db_query.py                 # 신규: docs/api.md §2.1 POST /internal/v1/db/query mock
    rag_search.py                # 신규: §2.6 POST /internal/v1/rag/search mock
    devices_internal.py          # 신규: §2.2/§2.3 devices/controls mock
    routine_tasks_internal.py    # 신규: §2.4/§2.5 routine-tasks mock
  state/
    agent_state.py       # 레거시 그래프들의 공유 AgentState
    chat_state.py         # 신규: ChatTurnState (messages/rounds 등 ReAct 루프 상태)
    report_turn_state.py  # 신규: ReportTurnState
  models/        # 레거시: Insight/HealthSummary/ActionPlan 등 내부 pydantic 모델
  services/      # LLM 클라이언트, 프롬프트 로더, Insight Synthesizer(레거시)
  prompts/       # 도메인별 LLM 프롬프트 템플릿
  clients/       # C++ 서버 API 공용 transport (get/post, 재시도, base_url override)
  routers/
    agent.py           # 레거시 /api/v1/agent/* 라우트
    chat.py            # 신규 POST /chat/v1/turns
    reports_turn.py    # 신규 POST /reports/v1/{domain}/{period}
  schemas/
    agent.py           # 레거시 request/response schema
    chat.py / report_turn.py / errors.py  # 신규 schema (docs/api.md 계약과 1:1)
  errors.py      # 신규: AgentApiError + api.md §4 에러 envelope 핸들러
  config.py      # 환경 변수 설정
  main.py        # FastAPI entrypoint (레거시 + 신규 라우터 동시 mount)
docs/
  api.md                 # 확정 계약 (이 문서 기준으로 구현)
  agent_architecture.md  # 레거시 아키텍처 설계(참고용)
  design.md
  interface.md
  db_updated.md / db_past.md
  schema.sql
```

## API 구현

### docs/api.md 계약 구현 (현재 기준, 신규)

```http
POST /chat/v1/turns                       # §1.1 — stream(기본 true, SSE) / stream:false(단일 JSON)
POST /reports/v1/{domain}/{period}        # §1.2 — domain: sleep|posture, period: daily|weekly
```

- `/chat/v1/turns`는 LLM이 `query_db`/`rag_search`/`list_devices`/`control_device`/`get_routine_tasks`/`update_routine_task` 중 필요한 tool을 스스로 판단해 호출하는 ReAct 루프입니다. SSE 이벤트(`tool.start`/`tool.end`/`message.delta`/`message.completed`/`[DONE]`/`error`)는 §1.1 규약을 그대로 따릅니다.
- `/reports/v1/{domain}/{period}`는 백엔드가 계산해 보낸 `metrics`/`raw`를 1차 소스로 사용하고, 패턴 설명에 더 넓은 맥락이 필요할 때만 내부적으로 `query_db`를 추가 호출합니다.
- §2 아웃바운드 tool(`db.query`/`devices`/`routine-tasks`/`rag.search`)은 백엔드 `/internal/v1/*`가 아직 없어 전부 **mock**입니다(`app/tools/db_query.py` 등). 실제 연동 시 `WAVEHOME_AGENT_INTERNAL_BASE_URL`만 바꾸면 됩니다.
- §1.3 `/llm/v1/*` OpenAI 호환 프록시는 **아직 미구현**입니다.

### 레거시 구현 (`docs/agent_architecture.md` 기준, 병행 운영 중)

```http
POST /api/v1/agent/chat
POST /api/v1/agent/reports/sleep/weekly
POST /api/v1/agent/reports/sleep/nightly
POST /api/v1/agent/reports/posture/weekly
POST /api/v1/agent/reports/posture/daily
POST /api/v1/agent/actions/recommend
```

키워드 매칭 기반 의도 분류 + 고정 그래프 라우팅을 사용하며, `docs/api.md`에는 없는 계약(`account_id` 문자열 사용, 비스트리밍 전용, `/actions/recommend` 등)입니다. 정리(삭제) 여부는 아직 결정되지 않아 당장은 그대로 유지합니다.

세부 요청/응답 스펙과 C++ 서버 연동 API 계약은 `docs/api.md`를 참고합니다. Postman으로 두 API 표면을 한 번에 테스트할 수 있는 컬렉션은 `docs/wavehome-agent.postman_collection.json`에 있습니다.

## TODO
- C++ 서버의 `/internal/v1/*`가 준비되면 `app/tools/db_query.py`/`rag_search.py`/`devices_internal.py`/`routine_tasks_internal.py`의 mock 분기를 실제 호출로 교체
- `docs/api.md` §1.3 `/llm/v1/*` OpenAI 호환 프록시 구현
- 레거시 `/api/v1/agent/*` 라우트·그래프(`supervisor_graph`/`action_graph`/`health_graph`/도메인 agent들) 정리 여부 결정 및 실행
- C++ 서버 API가 준비되면 레거시 `app/tools/*_api.py`의 mock 분기도 실제 엔드포인트로 교체
- 카메라/센서 관측 데이터 API가 생기면 `app/tools/observation_api.py`를 실제 연동으로 교체
- Human-in-the-Loop, LangGraph Checkpoint/Memory, LangSmith 추적 등 `docs/agent_architecture.md` §15의 향후 발전 방향 검토
