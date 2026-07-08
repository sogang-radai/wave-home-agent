# Agent Architecture

이 문서는 현재 코드에 구현된 에이전트 구조를 기준으로 하고, 두 가지 기능이 핵심이다.

- 채팅: 도메인 fan-out 후 필요하면 synthesize하는 chat graph
- 분석 작업: sleep/power 데이터를 받아 리포트 텍스트와 임베딩을 생성하는 job 흐름

## Runtime Shape

```text
FastAPI
  |
  +-- /chat/v1/turns
  |     |
  |     +-- app.graph.chat_runtime
  |           |
  |           +-- app.graph.turn_graph (gather -> Send fan-out -> synthesize)
  |                 |
  |                 +-- app.graph.domain_router (turn마다 1개 이상 도메인 분류)
  |                 +-- sleep/power/posture/iot/general 노드 (동시 실행, app.graph.chat_subgraphs 래핑)
  |                       |
  |                       +-- app.graph.tool_loop
  |                             |
  |                             +-- app.graph.domain_tools (도메인별 query_db/rag_search 스코프)
  |                             +-- query_db / rag_search / devices / routine tasks
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

채팅 한 turn은 `gather` -> 도메인별 동시 실행 -> `synthesize` 순서로 처리된다. 도메인 fan-out은 LangGraph의 `Send`로 구현되어 있다.

![turn graph](graphs/turn_graph.png)

처리 흐름은 다음과 같다.

1. **gather** 노드(`app/graph/turn_graph.py`)가 마지막 사용자 메시지를 `classify_domains`(`app/graph/domain_router.py`)에 전달한다. 분류 결과는 `state["domains"]`에 저장된다. 예를 들어 "이번 주 전반적인 건강 알려줘" 같은 질문은 `["sleep", "posture"]`처럼 여러 도메인으로 분류될 수 있다. 명확히 속하는 도메인이 없으면 `["general"]`을 사용한다.
2. `gather` 다음의 조건부 엣지 `_route_to_domains`는 `state["domains"]`의 각 도메인마다 `Send(domain, state)`를 하나씩 만든다. LangGraph는 이 `Send` 목록을 받아 같은 superstep 안에서 대상 노드들을 동시에 실행한다. 대상은 `sleep`, `power`, `posture`, `iot`, `general` 중 분류된 노드들이다. 별도의 `asyncio.gather` 없이 LangGraph 런타임이 병렬 실행을 담당한다.
3. 각 도메인 노드는 `_make_domain_node`가 만드는 wrapper다. 이 wrapper는 해당 도메인의 ReAct subgraph(`app/graph/chat_subgraphs.py`의 `build_domain_subgraph`)를 호출한 뒤, 결과를 두 채널로 반환한다. `messages`에는 전체 turn의 메시지를 합류시키고, `domain_answers`에는 `{domain, text}` 항목 하나를 추가한다. 여러 도메인 노드가 같은 step에서 동시에 `domain_answers`에 쓰기 때문에, `ChatTurnState.domain_answers`는 `operator.add` reducer로 선언되어 있다. reducer가 없으면 LangGraph가 동시 쓰기를 `InvalidUpdateError`로 처리한다.
4. **synthesize** 노드가 도메인 답변을 하나로 정리한다. 도메인이 하나뿐이면 추가 LLM 호출 없이 해당 도메인의 답변을 그대로 통과시킨다. 도메인이 둘 이상이면 `invoke_text`로 LLM을 한 번 더 호출해, 도메인 이름을 노출하지 않는 자연스러운 답변으로 병합한다.

각 도메인 subgraph는 같은 2노드 ReAct 루프를 사용한다. 이 루프는 `app/graph/tool_loop.py`의 `build_tool_loop`가 만든다. 도메인마다 달라지는 것은 tool 목록과 시스템 프롬프트뿐이다.

도메인별 tool 스코프는 `app/graph/domain_tools.py`에서 정의한다. `general`은 fallback 도메인으로, 기존 구조처럼 전체 tool을 사용할 수 있다. `query_db`와 `rag_search`는 도메인마다 별도 구현을 만들지 않는다. 대신 `make_query_db_tool(user_id, allowed_tables=...)`, `make_rag_search_tool(allowed_collections=...)`처럼 같은 tool 함수에 allowlist를 주입해서 재사용한다(`app/graph/tools.py`).

### SSE 스트리밍과 병렬 실행

도메인이 둘 이상이면 여러 도메인 노드가 동시에 실행된다. 각 도메인 subgraph의 내부 `agent` 노드도 동시에 LLM을 호출할 수 있다. 이 내부 토큰 스트림을 그대로 SSE로 내보내면 서로 다른 도메인의 텍스트가 한 답변 안에서 뒤섞인다.

이를 막기 위해 도메인 노드 wrapper는 멀티 도메인 turn에서 내부 subgraph 호출에 `config={"tags": [BACKGROUND_TAG]}`를 붙인다. `chat_runtime.py`는 이 태그가 붙은 chat-model 이벤트를 `message.delta`에서 제외한다.

그 결과 사용자에게 실시간으로 보이는 텍스트는 항상 하나다.

- 단일 도메인 turn: 해당 도메인 subgraph의 최종 답변
- 멀티 도메인 turn: `synthesize`가 만든 병합 답변

`tool.start`와 `tool.end` 이벤트는 숨기지 않는다. 따라서 사용자는 여러 도메인을 조사하는 진행 상황은 볼 수 있지만, 중간 답변 토큰이 섞여 보이지는 않는다.

이 태그 전파는 LangChain의 콜백 컨텍스트가 중첩된 subgraph 호출까지 전달된다는 점을 확인한 뒤 적용한 것이다. 도메인 노드를 `Send` 대상 노드로 등록하더라도, 그 안에서는 여전히 `subgraph.ainvoke()`를 중첩 호출한다. 그래서 이 태그 기반 필터링은 현재 구조에서도 필요하다.

### 도메인 subgraph 내부

`build_tool_loop`가 만드는 subgraph는 모든 도메인에서 같은 구조를 가진다. tool 목록과 시스템 프롬프트만 도메인별로 달라진다.

아래는 `sleep` subgraph를 렌더링한 예시다. 다른 도메인도 노드 구조는 동일하다.

![chat domain subgraph](graphs/chat_domain_subgraph.png)

### 도메인별 tool 스코프

| domain | query_db table allowlist | rag_search collection allowlist | 그 외 tool |
|---|---|---|---|
| sleep | `sleep_session`, `sleep_stat`, `sleep_report` | `sleep_report`, `sleep_stat` | - |
| power | `power_energy`, `power_report` | `power_report` | - |
| posture | `gesture_set`, `gesture_log` | (없음) | - |
| iot | `routine_task`, `device` | (없음) | `list_devices`, `control_device`, `get_routine_tasks`, `update_routine_task` |
| general | 전체 테이블 (allowlist 없음) | 전체 컬렉션 (allowlist 없음) | 위 6개 tool 전부 |

모델이 allowlist 밖의 `table`로 `query_db`를 호출하면 실제 DB까지 가지 않는다. `query_db`는 `db_query.py`와 같은 `INVALID_FILTER` shape으로 즉시 에러를 반환한다(`app/graph/tools.py`). `rag_search`는 allowlist 밖 collection을 조용히 드롭한다.

### 주요 진입점

- `app/routers/chat.py`
- `app/graph/chat_runtime.py`
- `app/graph/turn_graph.py` — `gather` -> `Send` fan-out -> 도메인 노드 -> `synthesize` 조립(`build_chat_graph(user_id)`), `BACKGROUND_TAG` 정의
- `app/graph/domain_router.py` — `classify_domains`로 다중 도메인 분류
- `app/graph/domain_tools.py` — 도메인별 tool 스코프 정의
- `app/graph/chat_subgraphs.py` — 도메인별 시스템 프롬프트와 `build_tool_loop` 조립
- `app/graph/tool_loop.py`

### Chat State

`ChatTurnState`는 `app/state/chat_state.py`에 정의되어 있다.

- `messages`: 최상위 turn의 메시지. 실행된 도메인 노드의 tool 호출 메시지가 여기로 모이고, `synthesize`가 최종 답변 메시지를 추가한다.
- `user_id`: 현재 사용자 ID.
- `chat_history_id`: 채팅 히스토리 ID.
- `now`: 요청 시점의 현재 시각 문자열.
- `retrieved`: 요청 전에 검색된 참고 자료.
- `model`: 요청에서 지정한 모델 이름.
- `rounds`: ReAct loop의 반복 횟수.
- `domains`: `gather`가 채우는 분류 결과. `_route_to_domains`가 이 값으로 `Send` 목록을 만든다.
- `domain_answers`: 각 도메인 노드가 반환하는 `{domain, text}` 목록. `operator.add`로 누적되며, `synthesize`가 병합 여부를 판단할 때 사용한다.

SSE 스트리밍은 LangGraph event stream을 `tool.start`, `tool.end`, `message.delta`, `message.completed` 이벤트로 변환한다. `stream:false` 요청은 같은 그래프를 동기 실행하고, 최종 content와 tool call 요약을 반환한다.

## Report Graph

`/reports/v1/{domain}/{period}`는 앱 화면에 표시할 구조화 리포트를 만든다. 백엔드가 계산한 `metrics`와 선택적 `raw`를 입력으로 받아 `summary`, `highlights`, `recommendations`를 반환한다.

진입점은 다음과 같다.

- `app/routers/reports_turn.py`
- `app/graph/report_turn_graph.py`
- `app/state/report_turn_state.py`

LLM 호출이 실패해도 rule-based fallback으로 응답할 수 있도록 설계되어 있다.

## Sleep/Power Analysis Jobs

`/sleep/v1/*`와 `/power/v1/*`는 앱 화면용 즉시 리포트가 아니다. 이 라우트들은 DB/RAG 적재용 텍스트를 생성한다.

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

Job state는 `app/services/jobs.py`의 in-memory dict에만 저장된다. 완료 또는 실패 후 24시간 보관되며, 서버가 재시작되면 유실된다.

## LLM Clients

- `app/services/llm.py`: Gemini 호출 래퍼. 채팅, report, job 텍스트 생성에서 사용한다.
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

`sleep_agent`, `posture_agent`, `observation_agent`, `lifestyle_agent`와 이들이 사용하는 mock tool/프롬프트는 남겨져 있다. 향후 ReAct 루프용 "도메인 insight tool"로 활용할 수 있기 때문이다.

백엔드의 자세/관측/생활 패턴 스키마가 준비되더라도, 이 코드를 공개 라우트에 직접 다시 붙이는 방식보다는, ReAct loop의 domain insight tool로 승격하는 방식이 더 잘 맞는다.
