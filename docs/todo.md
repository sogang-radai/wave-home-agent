# TODO

## 백엔드 연동

- `/internal/v1/db/query` 구현
- `/internal/v1/rag/search` 구현
- `/internal/v1/devices` 구현
- `/internal/v1/devices/{deviceId}/controls/{controlId}` 구현
- `/internal/v1/users/{userId}/routine-tasks` 구현
- `/internal/v1/routine-tasks/{taskId}` 구현
- `update_routine_task` non-mock transport를 문서 계약에 맞게 `PATCH`로 변경

## 데이터/스키마

- `DbTable` 허용 목록에 `device_control`, `posture_*`, `event` 추가
- 자세 도메인용 raw/stat/report 테이블 추가
- 자세 RAG collection 추가
- 카메라/관측 이벤트 테이블 추가
- 1회성 일정(`event`)과 반복 루틴(`routine_task`)을 함께 다루는 조회/수정 contract 확정

## 리포트/분석

- 앱 화면용 인사이트 리포트는 `POST /reports/v1/{domain}/{period}` 계약으로 구현할지 논의, 확정되면 `power` 도메인을 앱 화면용 `POST /reports/v1/{domain}/{period}` 패턴에도 포함해야 함.
- job 상태 저장소 개선 검토: 현재 `app/services/jobs.py`의 프로세스 인메모리 `dict`만 사용하므로 서버 재시작 또는 다중 프로세스에서 상태가 유실된다
- `embed:true` 개발/운영 경로 점검: `OLLAMA_BASE_URL` 연결 실패 시 job이 `GENERATION_FAILED` 또는 `GENERATION_TIMEOUT`으로 끝난다

## 문서/운영

- `/llm/v1/models`에서 Ollama `/api/tags` 응답에 embedding dimension이 없을 때의 표시 방식을 확정

## 확장 후보

- Agentic RAG: 한 턴 안에서 `rag.search`를 검색, 평가, 재검색 순서로 최대 2~3회까지 반복
- `sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`를 ReAct 루프의 domain insight tool로 승격
- Human-in-the-loop, LangGraph checkpoint/memory, LangSmith 추적 도입 검토
