# WaveHome Agent Server

WaveHome의 에이전트 서버입니다.

프론트엔드와 직접 연동하는 일반 백엔드 서버가 아니라, C++ 서버가 호출하는 AI 에이전트 서버로 동작합니다. 사용자의 수면, 자세, 카메라 기반 관측 데이터, 일정, 가전 상태 등은 C++ 서버가 관리하며, 이 서버는 C++ 서버가 제공하는 API를 통해 필요한 데이터만 간접 조회하고 액션 요청을 전달합니다.

## 서버 역할

이 서버의 책임은 LangGraph 기반 에이전트 플로우를 실행해 채팅 응답, 건강 인사이트, 리포트, 권장 액션, 가전 제어 의도를 생성하는 것입니다.

> **API 계약 현황**: `docs/api.md`가 백엔드-에이전트 계약의 확정안이며, 이 서버는 그 계약(`/chat/v1/turns`, `/reports/v1/{domain}/{period}`)을 그대로 구현합니다 — LLM이 직접 tool 호출 여부를 판단하는 ReAct 루프, SSE 스트리밍. 초기 설계(`docs/agent_architecture.md`, 키워드 기반 라우팅 + 고정 그래프)를 따르던 레거시 `/api/v1/agent/*` 라우트와 그 그래프/agent들은 정리되었습니다. 다만 `sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`와 이들이 쓰는 mock tool·프롬프트는 향후 ReAct 루프용 "도메인 insight tool"로 승격할 가치가 있어 코드는 남겨뒀고, 현재는 어떤 라우트에도 연결되어 있지 않습니다.

### 1. 채팅

사용자와의 자연어 대화를 처리합니다.

채팅에서는 C++ 서버 API를 통해 수집 및 저장된 데이터를 조회한 뒤, 다음과 같은 응답을 생성합니다.

- 수면 데이터 기반 건강 상담 — 구현됨(`query_db`의 `sleep_session`/`sleep_stat`/`sleep_report` + `rag_search`의 `sleep_report`/`sleep_stat`)
- 사용자의 현재 상태와 최근 이력에 맞춘 권장 행동 — 구현됨(위 수면 데이터 기반. 자세/생활 패턴 데이터는 아직 없어 그만큼은 반영 못 함)
- 일정 변경 요청 해석 및 실행 요청 — 구현됨(`get_routine_tasks`/`update_routine_task`)
- 가전 제어 요청 해석 및 실행 요청 — 구현됨(`list_devices`/`control_device`)
- 자세 데이터 기반 피드백, 카메라/센서 관측 데이터 기반 생활 인사이트 — **아직 미구현**. `app/tools/db_query.py`(허용 테이블)와 `app/tools/rag_search.py`(허용 컬렉션) 어디에도 자세/관측 데이터 소스가 없어서, LLM이 tool을 시도해도 항상 빈 결과만 받고 "데이터가 없다"고 답합니다(백엔드에 posture 스키마·카메라 이벤트 테이블이 아직 없기 때문 — TODO 참고)


예시 요청(위 두 항목은 아직 실제 데이터로 답하지 못함):

```text
어젯밤 수면 어땠어?
요즘 자세가 안 좋은 편이야?      # 아직 미구현 — "데이터 없음"으로만 응답
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

# sleep_agent/posture_agent/lifestyle_agent(app/tools/{sleep,posture,schedule}_api.py)가 사용.
# observation_api.py는 카메라 이벤트 백엔드 테이블이 아직 없어 이 값을 읽지 않고 항상 mock만 반환합니다.
WAVEHOME_CORE_API_BASE_URL=http://127.0.0.1:9000
WAVEHOME_CORE_API_TIMEOUT_MS=5000
WAVEHOME_CORE_API_MOCK=true

# docs/api.md §2 /internal/v1/* 아웃바운드 tool(db.query, devices, routine-tasks, rag.search)이 사용
WAVEHOME_AGENT_INTERNAL_BASE_URL=http://127.0.0.1:8500/internal/v1

# docs/api.md §1.3 /llm/v1/* 프록시가 포워딩할 Ollama 서버 주소 (OpenAI 호환 /v1/* 필요).
# 실제 팀 공유 주소는 .env에만 넣고 커밋하지 마세요.
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_MS=30000
```

`WAVEHOME_CORE_API_MOCK=true`이면 C++ 서버가 아직 준비되지 않아도 mock context로 LangGraph 플로우를 실행할 수 있습니다. C++ 서버 API 연동이 준비되면 이 값을 `false`로 바꾸고 `app/clients/core.py`의 엔드포인트를 실제 스펙에 맞추면 됩니다.

`docs/api.md` §2의 새 outbound tool(`app/tools/db_query.py`, `rag_search.py`, `devices_internal.py`, `routine_tasks_internal.py`)도 같은 `CoreApiClient.is_mock` 패턴을 쓰지만, 백엔드의 `/internal/v1/*`가 아직 없어 지금은 항상 mock 데이터를 반환합니다. 실제 백엔드가 준비되면 `WAVEHOME_AGENT_INTERNAL_BASE_URL`만 맞는 주소로 바꾸면 됩니다(코드 변경 불필요).

`OLLAMA_BASE_URL`은 실제 Ollama 서버(OpenAI 호환 `/v1/*` 활성화됨, `nomic-embed-text` + `gemma2:2b`/`gemma4:12b-mlx` 서빙 중)를 가리켜야 `/llm/v1/*`가 동작합니다.

## 프로젝트 구조

```text
app/
  graph/
    tool_loop.py       # LLM이 tool 호출 여부를 스스로 판단하는 2노드 ReAct 루프(공용)
    turn_graph.py      # /chat/v1/turns용 tool_loop 인스턴스 + 시스템 프롬프트
    tools.py           # LangChain @tool 래퍼 (build_tools(user_id))
    chat_runtime.py    # SSE/비스트리밍 드라이버 (astream_events -> tool.start/tool.end/message.delta)
    report_turn_graph.py  # /reports/v1/{domain}/{period}용 그래프 (metrics/raw 인라인 소비)
  agents/
    sleep_agent.py / posture_agent.py / observation_agent.py / lifestyle_agent.py
                       # 도메인별 데이터 조회 + insight 생성 로직. 현재 어떤 라우트/그래프에도
                       # 연결돼 있지 않음 — 향후 ReAct 루프의 "도메인 insight tool"로 승격 예정
  tools/
    sleep_api.py / posture_api.py / observation_api.py / schedule_api.py
                       # 위 4개 agent가 쓰는 mock 데이터 소스 (옛 /api/v1/agent/* 계약 기준 shape)
    db_query.py                 # docs/api.md §2.1 POST /internal/v1/db/query mock
    rag_search.py                # §2.6 POST /internal/v1/rag/search mock
    devices_internal.py          # §2.2/§2.3 devices/controls mock
    routine_tasks_internal.py    # §2.4/§2.5 routine-tasks mock
  state/
    agent_state.py       # 위 4개 agent가 쓰는 공유 상태 타입
    chat_state.py         # ChatTurnState (messages/rounds 등 ReAct 루프 상태)
    report_turn_state.py  # ReportTurnState
  models/
    insight.py     # 위 4개 agent가 만드는 Insight 모델
  services/      # LLM 클라이언트, 프롬프트 로더
  prompts/       # 도메인별 LLM 프롬프트 템플릿 (sleep/posture/observation/lifestyle/report)
  clients/
    core.py        # C++ 서버 API 공용 transport (get/post, 재시도, base_url override)
    ollama.py      # Ollama OpenAI 호환 /v1/* transport (/llm/v1/* 프록시가 사용)
  routers/
    chat.py            # POST /chat/v1/turns
    reports_turn.py    # POST /reports/v1/{domain}/{period}
    llm.py              # GET /llm/v1/models, POST /chat/completions, POST /embeddings
  schemas/
    chat.py / report_turn.py / errors.py / llm.py  # docs/api.md 계약과 1:1 대응하는 schema
  errors.py      # AgentApiError + api.md §4 에러 envelope 핸들러
  config.py      # 환경 변수 설정
  main.py        # FastAPI entrypoint
docs/
  api.md                 # 확정 계약 (이 문서 기준으로 구현)
  agent_architecture.md  # 이전 아키텍처 설계(참고용, 코드는 정리됨)
  design.md
  interface.md
  db_updated.md / db_past.md
  schema.sql
```

## API 구현
postman documentation: https://documenter.getpostman.com/view/42800287/2sBY4JvhRh

```http
POST /chat/v1/turns                       # §1.1 — stream(기본 true, SSE) / stream:false(단일 JSON)
POST /reports/v1/{domain}/{period}        # §1.2 — domain: sleep|posture, period: daily|weekly
GET  /llm/v1/models                       # §1.3 — Ollama 서빙 모델 목록 (role: chat|embedding)
POST /llm/v1/chat/completions             # §1.3 — OpenAI 호환, stream 지원
POST /llm/v1/embeddings                   # §1.3 — OpenAI 호환, 스트리밍 없음
```

- `/chat/v1/turns`는 LLM이 `query_db`/`rag_search`/`list_devices`/`control_device`/`get_routine_tasks`/`update_routine_task` 중 필요한 tool을 스스로 판단해 호출하는 ReAct 루프입니다. SSE 이벤트(`tool.start`/`tool.end`/`message.delta`/`message.completed`/`[DONE]`/`error`)는 §1.1 규약을 그대로 따릅니다.
- `/reports/v1/{domain}/{period}`는 백엔드가 계산해 보낸 `metrics`/`raw`를 1차 소스로 사용하고, 패턴 설명에 더 넓은 맥락이 필요할 때만 내부적으로 `query_db`를 추가 호출합니다.
- §2 아웃바운드 tool(`db.query`/`devices`/`routine-tasks`/`rag.search`)은 백엔드 `/internal/v1/*`가 아직 없어 전부 **mock**입니다(`app/tools/db_query.py` 등). 실제 연동 시 `WAVEHOME_AGENT_INTERNAL_BASE_URL`만 바꾸면 됩니다.
- `/llm/v1/*`는 팀에서 공유한 Ollama 서버(OpenAI 호환 `/v1/*`)로의 얇은 프록시입니다(`app/clients/ollama.py`). `GET /models`는 Ollama의 `/api/tags`(`capabilities` 필드로 chat/embedding 구분)를 우리 shape로 매핑하고, `chat/completions`/`embeddings`는 대부분 그대로 전달합니다. 에러는 상태코드 기준으로 매핑합니다: 404→`MODEL_NOT_FOUND`, timeout→`LLM_TIMEOUT`, 그 외→`LLM_PROVIDER_ERROR` (스트리밍 중 에러는 `data: {"error":{...}}\n\n` 이벤트로).

세부 요청/응답 스펙과 C++ 서버 연동 API 계약은 `docs/api.md`를 참고합니다.

## TODO
- C++ 서버의 `/internal/v1/*`가 준비되면 `app/tools/db_query.py`/`rag_search.py`/`devices_internal.py`/`routine_tasks_internal.py`의 mock 분기를 실제 호출로 교체
- `sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`를 `/chat/v1/turns` ReAct 루프의 tool(예: `get_sleep_insight`)로 승격 — 단, 지금은 옛 mock(`sleep_api.py` 등)을 쓰고 있어 새 `db_query` mock으로 데이터 소스를 먼저 갈아끼워야 하고, `invoke_structured` LLM 호출을 그대로 tool 안에 둘지(문장 품질↑, 턴당 LLM 호출↑) 각 agent의 `_rule_based_insight` 규칙 기반 로직만 쓸지(호출 비용 없음) 결정 필요
- C++ 서버 API가 준비되면 위 4개 agent가 쓰는 `app/tools/{sleep,posture,observation,schedule}_api.py`의 mock 분기도 실제 엔드포인트로 교체
- 카메라/센서 관측 데이터 API가 생기면 `app/tools/observation_api.py`를 실제 연동으로 교체
- Human-in-the-Loop, LangGraph Checkpoint/Memory, LangSmith 추적 등 `docs/agent_architecture.md` §15의 향후 발전 방향 검토
