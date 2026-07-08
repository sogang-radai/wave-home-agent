# TODO

## 백엔드 연동

- `/internal/v1/db/query` 구현
- `/internal/v1/rag/search` 구현
- `/internal/v1/devices` 구현
- `/internal/v1/devices/{deviceId}/controls/{controlId}` 구현
- `/internal/v1/users/{userId}/routine-tasks` 구현
- `/internal/v1/routine-tasks/{taskId}` 구현
- `update_routine_task` non-mock transport를 문서 계약에 맞게 `PATCH`로 변경
- 위 엔드포인트가 준비되면 `WAVEHOME_AGENT_INTERNAL_BASE_URL`을 실제 주소로 바꾸고 `db_query`/`rag_search`/`devices_internal`/`routine_tasks_internal`의 mock 응답과 실제 응답 스키마가 맞는지 검증

## 데이터/스키마

- `DbTable` 허용 목록에 `device_control`, `posture_*`, `event` 추가
- 자세 도메인용 raw/stat/report 테이블 추가 (`/reports/v1/{domain}/{period}`의 `domain` enum에는 이미 `posture`가 정의돼 있어 데이터만 없는 상태)
- 자세 RAG collection 추가
- 카메라/관측 이벤트 테이블 추가 (`app/tools/observation_api.py`는 `sleep_api.py`/`posture_api.py`/`schedule_api.py`와 달리 `CoreApiClient` 분기 자체가 없는 mock 전용 코드라, 테이블이 생겨도 분기 전환이 아니라 실제 호출 구현을 새로 붙여야 함)
- 관측/생활 패턴 데이터용 RAG collection 추가 (현재 계획된 RAG collection은 `sleep_report`/`sleep_stat`/자세용뿐이라 카메라·생활 패턴 쪽은 채팅 tool에서 아예 조회할 수 없음)
- 1회성 일정(`event`)과 반복 루틴(`routine_task`)을 함께 다루는 조회/수정 contract 확정

## 리포트/분석

- 앱 화면용 인사이트 리포트는 `POST /reports/v1/{domain}/{period}` 계약으로 구현할지 논의, 확정되면 `power` 도메인을 앱 화면용 `POST /reports/v1/{domain}/{period}` 패턴에도 포함해야 함.
- job 상태 저장소 개선 검토: 현재 `app/services/jobs.py`의 프로세스 인메모리 `dict`만 사용하므로 서버 재시작 시 상태가 유실되고, 여러 프로세스로 수평 확장하면 job이 프로세스별로 분리돼 폴링이 어긋난다. 이 서버는 SQLite에 직접 접근하지 않는 원칙이라 영속화하려면 백엔드에 위임하거나 Redis 등 별도 저장소 도입이 필요
- `embed:true` 개발/운영 경로 점검: `OLLAMA_BASE_URL` 연결 실패 시 job이 `GENERATION_FAILED` 또는 `GENERATION_TIMEOUT`으로 끝난다 (로컬에 Ollama가 없으면 `embed:false`로 호출해 우회 가능하다는 점을 문서에도 명시)
- `power` 도메인에 `summaries` 엔드포인트가 필요한지 확인: 현재 `sleep`은 `summaries`+`reports`가 모두 있지만 `power`는 `reports`만 있음 — 의도된 비대칭인지 확정

## 문서/운영

- `/llm/v1/models`에서 Ollama `/api/tags` 응답에 embedding dimension이 없을 때의 표시 방식을 확정

## 확장 후보

- Agentic RAG: 한 턴 안에서 `rag.search`를 검색, 평가, 재검색 순서로 최대 2~3회까지 반복
- `sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`를 ReAct 루프의 domain insight tool로 승격 — 단, 지금은 옛 mock(`sleep_api.py` 등)을 쓰고 있어 새 `db_query` mock으로 데이터 소스를 먼저 교체해야 하고, 각 agent의 `invoke_structured` LLM 호출을 tool 안에 그대로 둘지(문장 품질↑, 턴당 LLM 호출↑) `_rule_based_insight`만 쓸지(호출 비용 없음) 결정 필요
- Human-in-the-loop, LangGraph checkpoint/memory, LangSmith 추적 도입 검토
