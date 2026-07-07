# Agent Architecture

이 문서는 현재 구현된 구조를 기준으로 한다. 초기 설계의 Supervisor/Multi-Agent 구조는 코드 일부로 남아 있지만, 공개 라우트의 중심은 ReAct tool loop와 분석 job이다.

## Runtime Shape

```text
FastAPI
  |
  +-- /chat/v1/turns
  |     |
  |     +-- app.graph.chat_runtime
  |           |
  |           +-- app.graph.turn_graph
  |                 |
  |                 +-- app.graph.tool_loop
  |                       |
  |                       +-- query_db / rag_search / devices / routine tasks
  |
  +-- /reports/v1/{domain}/{period}
  |     |
  |     +-- app.graph.report_turn_graph
  |
  +-- /sleep/v1/*, /power/v1/*
  |     |
  |     +-- app.services.jobs
  |     +-- app.services.sleep_analysis / power_analysis
  |     +-- app.services.embeddings
  |
  +-- /llm/v1/*
        |
        +-- app.clients.ollama
```

## Chat Graph

채팅은 LLM이 필요한 tool을 직접 선택하는 2노드 ReAct 루프다.

```text
START
  |
  v
agent: LLM with bound tools
  |
  +-- tool call exists --> tools
  |                         |
  |                         v
  |                       agent
  |
  +-- no tool call ------> END
```

진입점:

- `app/routers/chat.py`
- `app/graph/chat_runtime.py`
- `app/graph/turn_graph.py`
- `app/graph/tool_loop.py`

State:

- `messages`
- `user_id`
- `chat_history_id`
- `now`
- `retrieved`
- `model`
- `rounds`

SSE는 LangGraph event stream을 `tool.start`, `tool.end`, `message.delta`, `message.completed`로 변환한다. `stream:false`는 같은 그래프를 동기 실행하고 최종 content와 tool call 요약을 반환한다.

## Report Graph

`/reports/v1/{domain}/{period}`는 앱 화면 표시용 구조화 리포트를 만든다. 백엔드가 계산한 `metrics`와 선택적 `raw`를 입력으로 받아 `summary`, `highlights`, `recommendations`를 반환한다.

진입점:

- `app/routers/reports_turn.py`
- `app/graph/report_turn_graph.py`
- `app/state/report_turn_state.py`

LLM 호출이 실패해도 rule-based fallback으로 응답할 수 있도록 설계되어 있다.

## Sleep/Power Analysis Jobs

`/sleep/v1/*`와 `/power/v1/*`는 앱 화면용 즉시 리포트가 아니라 DB/RAG 적재용 텍스트를 만든다.

```text
POST request
  |
  v
validate input
  |
  v
JobStore.create()
  |
  v
202 { jobId, status: queued }
  |
  v
background task
  |
  +-- invoke_text() with rule-based fallback
  +-- generate_embedding() when embed=true
  +-- JobStore.complete() or fail()
```

Job state는 `app/services/jobs.py`의 in-memory dict에만 저장된다. 완료/실패 후 24시간 보관되며 서버 재시작 시 유실된다.

## LLM Clients

- `app/services/llm.py`: Gemini 호출 래퍼. 채팅과 report/job 텍스트 생성에서 사용한다.
- `app/clients/ollama.py`: Ollama/OpenAI 호환 API transport. `/llm/v1/*` 프록시와 임베딩 job에서 사용한다.

## Legacy Domain Agents

다음 파일들은 현재 공개 라우트에 연결되어 있지 않다.

- `app/agents/sleep_agent.py`
- `app/agents/posture_agent.py`
- `app/agents/observation_agent.py`
- `app/agents/lifestyle_agent.py`
- `app/tools/sleep_api.py`
- `app/tools/posture_api.py`
- `app/tools/observation_api.py`
- `app/tools/schedule_api.py`

`sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`와 이들이 쓰는 mock tool·프롬프트는 향후 ReAct 루프용 "도메인 insight tool"로 활용될 경우를 대비하여 코드는 남겨져 있다.

향후 백엔드 자세/관측/생활 패턴 스키마가 준비되면, 이 코드를 직접 라우트에 다시 붙이기보다 ReAct loop의 domain insight tool로 승격하는 편이 현재 구조와 잘 맞는다.
