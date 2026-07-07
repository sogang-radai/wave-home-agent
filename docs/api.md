# Agent Server API
이 문서는 채팅과 인사이트 리포트 기능 구현을 위한 API 계약을 정의한다.

| 문서 | 범위 | 주요 엔드포인트 |
| --- | --- | --- |
| [api1.md](./api1.md) | 백엔드 → 에이전트 API | `/chat/v1/turns`, `/reports/v1/{domain}/{period}`, `/llm/v1/*`, `/sleep/v1/*`, `/power/v1/*` |
| [api2.md](./api2.md) | 에이전트 → 백엔드 API, 공통 기준, 테스트 | `/internal/v1/db/query`, `/internal/v1/devices/*`, `/internal/v1/routine-tasks/*`, `/internal/v1/rag/search` |

## 전체 목차

- [아키텍처 개요](#아키텍처-개요)
- [1. 백엔드 → 에이전트 API](./api1.md#1-백엔드--에이전트-api)
  - [1.1 채팅](./api1.md#11-채팅)
  - [1.2 인사이트 리포트](./api1.md#12-인사이트-리포트)
  - [1.3 LLM 포워딩 API](./api1.md#13-llm-포워딩-api)
  - [1.4 Sleep/Power 분석 API](./api1.md#14-sleeppower-분석-api-job-패턴)
- [2. 에이전트 → 백엔드 API](./api2.md#2-에이전트--백엔드-api)
  - [2.1 DB 조회](./api2.md#21-db-조회)
  - [2.2 기기 조회](./api2.md#22-기기-조회)
  - [2.3 기기 제어](./api2.md#23-기기-제어)
  - [2.4 일정 조회](./api2.md#24-일정-조회)
  - [2.5 일정 변경](./api2.md#25-일정-변경)
  - [2.6 RAG 검색](./api2.md#26-rag-검색)
- [3. 리포트 생성 내용 기준](./api2.md#3-리포트-생성-내용-기준)
- [4. 에러 응답](./api2.md#4-에러-응답)
- [5. 구현 매핑](./api2.md#5-구현-매핑)
- [6. 테스트 시나리오](./api2.md#6-테스트-시나리오)


## 아키텍처 개요

- 백엔드(C++ Drogon, :8500)가 유일한 공개 게이트웨이다. 프론트엔드는 백엔드만 호출한다.
- Agent Server(FastAPI + LangGraph, :8501)는 내부 전용 서버다. 백엔드가 호출할 때만 동작하며, 프론트엔드와 직접 통신하지 않는다.
- Agent Server는 SQLite DB에 직접 접근하지 않는다. 수면, 자세, 카메라/센서 관측, 일정, 가전 상태 등 DB에 저장된 데이터는 백엔드가 소유하며, Agent Server는 백엔드 내부 API를 통해서만 조회하거나 실행 요청을 보낸다.
- 사용자 식별은 `userId`(INTEGER)를 기준으로 한다. `accountId`(문자열) 등 프론트엔드 전용 표현은 백엔드 계층에서만 다루고, 백엔드-에이전트 계약에는 등장하지 않는다.
- 날짜는 `YYYY-MM-DD`, 시각은 `YYYY-MM-DD HH:MM:SS` 형식을 사용한다(DB 스키마와 동일한 포맷).
- 기간 조회의 `from`/`to`는 반열림 `[from, to)`으로 해석한다(백엔드 DB 조회 API 규약과 통일).
- 모든 응답은 JSON이며, `Content-Type: application/json`을 사용한다(SSE 구간 제외).

### 호출 방향과 동작 흐름

한 번의 채팅 턴 처리 안에서 커넥션 2종류가 동시에 열린다.

- **백엔드 → 에이전트** (긴 연결 1개): 턴 실행 요청이자 답변을 스트리밍으로 되돌려받는 채널.
- **에이전트 → 백엔드** (짧은 동기 HTTP 여러 개): LangGraph가 tool을 호출할 때마다 나가는 별개 요청.

```text
프론트 → 백엔드(:8500) → 에이전트(:8501)   POST /chat/v1/turns (연결 하나가 계속 열려 있음)
                              │
                              ├─ LLM 판단: 데이터가 필요하다
                              ├─ 에이전트 → 백엔드: POST /internal/v1/db/query   (짧은 동기 호출)
                              ├─ LLM: 받은 데이터로 계속 추론
                              ├─ (필요 시) 에이전트 → 백엔드: 기기 제어 / 일정 변경 실행 요청
                              └─ LLM: 최종 답변 생성 → 열려 있던 연결로 스트리밍
```

이는 새로운 요청 사이클이 아니라 **첫 요청을 처리하는 도중에 나가는 부수 요청**이다. `LLM → tool 필요 판단 → tool 실행(백엔드 호출) → 결과를 LLM에 반영 → 반복 → 최종 답변` 루프가 그대로 이 구조에 대응한다.

리포트 생성은 조금 다르다. 백엔드가 리포트 대상(사용자·기간)을 요청 시점에 이미 알고 있으므로, 백엔드가 지표(metrics)까지 계산해 인라인으로 넘긴다. 에이전트는 그 데이터로 자연어를 생성하는 것이 기본 경로이고, 더 넓은 맥락이 필요할 때만 `db.query`를 추가로 호출한다([§2.1](./api2.md#21-db-조회) 참고).

### Agent Server가 구현해야 하는 두 방향

| 방향 | 역할 | 코드 위치(예정) |
|---|---|---|
| 백엔드 → 에이전트 (인바운드, 에이전트가 서버) | `/chat/v1/turns`, `/reports/v1/{domain}/{period}` 라우트 처리 | `app/routers/` |
| 백엔드 → 에이전트 (인바운드, LLM 포워딩) | `/llm/v1/models` \| `/llm/v1/chat/completions` \| `/llm/v1/embeddings` — 백엔드가 챗 턴 외 용도(대시보드 문구 생성 등)로 LLM을 쓸 때 경유하는 OpenAI 호환 프록시. [§1.3](./api1.md#13-llm-포워딩-api) 참고 | `app/routers/llm.py` |
| 백엔드 → 에이전트 (인바운드, 수면/전력 분석 job) | `/sleep/v1/summaries` \| `/sleep/v1/reports` \| `/sleep/v1/jobs/{jobId}`, `/power/v1/reports` \| `/power/v1/jobs/{jobId}` — RAG 코퍼스용 원본 텍스트+임베딩을 비동기로 생성. [§1.4](./api1.md#14-sleeppower-분석-api-job-패턴) 참고 | `app/routers/sleep_analysis.py`, `app/routers/power_analysis.py` |
| 에이전트 → 백엔드 (아웃바운드, 에이전트가 클라이언트) | DB 조회·RAG 검색·기기 제어·일정 조회/변경을 httpx로 호출 | `app/tools/*_api.py`, `app/clients/core.py` |
