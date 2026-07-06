# WaveHome Agent Server API

이 문서는 채팅과 인사이트 리포트 기능 구현을 위한 API 계약을 정의한다.

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

리포트 생성은 조금 다르다. 백엔드가 리포트 대상(사용자·기간)을 요청 시점에 이미 알고 있으므로, 백엔드가 지표(metrics)까지 계산해 인라인으로 넘긴다. 에이전트는 그 데이터로 자연어를 생성하는 것이 기본 경로이고, 더 넓은 맥락이 필요할 때만 `db.query`를 추가로 호출한다(§2.2 참고).

### Agent Server가 구현해야 하는 두 방향

| 방향 | 역할 | 코드 위치(예정) |
|---|---|---|
| 백엔드 → 에이전트 (인바운드, 에이전트가 서버) | `/chat/v1/turns`, `/reports/v1/{domain}/{period}` 라우트 처리 | `app/routers/` |
| 백엔드 → 에이전트 (인바운드, LLM 포워딩) | `/llm/v1/models`\|`chat/completions`\|`embeddings` — 백엔드가 챗 턴 외 용도(대시보드 문구 생성 등)로 LLM을 쓸 때 경유하는 OpenAI 호환 프록시. §1.3 참고 | `app/routers/llm.py` |
| 에이전트 → 백엔드 (아웃바운드, 에이전트가 클라이언트) | DB 조회·RAG 검색·기기 제어·일정 조회/변경을 httpx로 호출 | `app/tools/*_api.py`, `app/clients/core.py` |

`/llm/v1/*`는 백엔드(C++) 명세서의 설계를 채택한다.

---

## 1. 백엔드 → 에이전트 API

기본 경로 예시:

```text
http://127.0.0.1:8501
```

### 1.1 채팅

```http
POST /chat/v1/turns
```

한 번의 대화 턴을 실행한다. `stream`(기본 `true`)이면 **SSE**로 토큰을 스트리밍하고, `false`면 완성된 답변을 단일 JSON으로 반환한다.

백엔드는 `chat_history`(또는 `conversation`)에서 불러온 대화 이력을 `messages`로만 구성해 전달한다. RAG나 원천 데이터 조회는 에이전트가 tool로 직접 수행하므로, 백엔드가 미리 데이터를 넣어줄 필요는 없다.

#### Request

```json
{
  "chatHistoryId": 42,
  "userId": 1,
  "messages": [
    { "role": "user", "content": "어젯밤 수면 어땠어?" }
  ],
  "context": {
    "now": "2026-07-06 09:30:00"
  },
  "stream": true
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `chatHistoryId` | number | Y | 대화 세션 ID (백엔드 DB의 대화 식별자) |
| `userId` | number | Y | 사용자 ID |
| `messages` | array | Y | `{ role: 'system'\|'user'\|'assistant', content: string }[]` |
| `context.now` | string | N | 현재 시각. "어제"·"오늘 밤" 등 상대 시점 해석에 사용 |
| `context.retrieved` | array | N | `{ collection, refId?, text }[]`. 턴 시작 **전** 백엔드가 §2.6으로 미리 검색해 넣는 사전검색 스니펫(지연시간 최적화용 옵션). 기본 흐름에서는 비워 두고, 에이전트가 턴 중 RAG tool로 직접 가져오는 것이 정식 경로다 |
| `model` | string | N | 선호 모델. 강제가 아니라 힌트이며 실제 사용 모델은 `message.completed.model`로 돌아온다 |
| `stream` | boolean | N | 기본 `true` |

#### Response 200 (SSE)

```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

```text
data: {"type":"tool.start","name":"query_db","args":{"table":"sleep_session"}}

data: {"type":"tool.end","name":"query_db","ok":true,"result":{"count":1}}

data: {"type":"message.delta","content":"어젯밤 수면 점수는 78점이고, "}

data: {"type":"message.delta","content":"총 수면 시간은 6시간 55분이었어요."}

data: {"type":"message.completed","content":"어젯밤 수면 점수는 78점이고, 총 수면 시간은 6시간 55분이었어요. 중간 각성이 3회 있었습니다.","model":"gemini-3.1-flash-lite"}

data: [DONE]
```

스트리밍 규칙:

- 각 이벤트는 `data: <json>\n\n` 형식이다.
- `message.delta.content`를 누적하면 최종 답변이 된다. `tool.start`/`tool.end`는 진행 표시용이다. `tool.end.result`는 옵션(툴 결과 요약).
- thinking 모델은 `message.delta.reasoning`으로 추론 구간을 별도 전송할 수 있다(옵션, 최종 답변에는 포함하지 않음).
- 종료는 반드시 `data: [DONE]\n\n`으로 마무리한다.
- 스트림 시작 후 오류는 `data: {"type":"error","error":{...}}\n\n`을 보낸 뒤 연결을 닫는다.
- 백엔드가 연결을 끊으면 에이전트는 진행 중인 그래프 실행을 취소한다.
- 기본 tool 목록: `db.query`(§2.1), `rag.search`(§2.6), 기기 제어(§2.2/2.3), 일정 조회/변경(§2.4/2.5).

#### 의도 예시

| 사용자 요청 | 처리 |
| --- | --- |
| `어젯밤 수면 어땠어?` | 수면 데이터 조회 후 건강 상담 |
| `요즘 자세가 안 좋은 편이야?` | 자세 데이터 조회 후 피드백 |
| `밤 11시에 불 소등해줘.` | 기기 상태 조회 후 제어 실행 요청 |
| `에어컨 온도 조금 낮춰줘.` | 기기 상태 조회 후 제어 실행 요청 |
| `오늘 밤 운동 일정을 내일로 옮겨줘.` | 일정 조회 후 변경 요청 |

가전 제어와 일정 변경은 에이전트가 직접 DB를 수정하지 않고, LangGraph tool을 통해 §2의 백엔드 API로 실행을 요청한다.

#### Response 400

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "messages 는 최소 1개 이상이어야 합니다.",
    "field": "messages"
  }
}
```

### 1.2 인사이트 리포트

```http
POST /reports/v1/{domain}/{period}
```

`domain`: `sleep` | `posture`
`period`: `daily` | `weekly`

> `posture`는 현재 백엔드 스키마(`db_updated.md`)와 `DbTable` 목록 어디에도 없다(옛 설계 `db_past.md`에만 있던 테이블). 백엔드에 자세 스키마 이관 및 이 리포트 API 구현을 별도로 요청해야 한다 — 제안 스키마는 `db_updated.md`의 "자세 트래킹" 절 참고.

대상 리포트는 이 하나의 패턴으로 4종을 모두 표현한다.

| 경로 | 의미 |
| --- | --- |
| `POST /reports/v1/sleep/daily` | 어젯밤 수면 리포트 |
| `POST /reports/v1/sleep/weekly` | 이번 주 수면 리포트 |
| `POST /reports/v1/posture/daily` | 오늘의 자세 리포트 |
| `POST /reports/v1/posture/weekly` | 이번 주 자세 리포트 |

백엔드는 해당 사용자·기간의 **지표(metrics)를 직접 계산해 인라인으로 전달**한다. 지표 계산 로직을 백엔드에만 두어, 대시보드/차트에 쓰는 숫자와 리포트 문장의 숫자가 어긋나지 않도록 한다. 에이전트는 전달받은 데이터로 자연어를 생성하는 것이 기본이며, 더 넓은 맥락이 필요하면(예: 이번 주 패턴을 설명하려고 지난달 데이터도 참고) `POST /internal/v1/db/query`(§2.1)를 추가로 호출할 수 있다.

#### Request

```json
{
  "userId": 1,
  "periodStart": "2026-06-29",
  "metrics": {
    "averageScore": 74,
    "avgSleepMinutes": 402,
    "wakeUps": 3
  },
  "raw": {
    "sessions": [
      { "date": "2026-07-05", "score": 78, "actualSleepMinutes": 415, "wakeUps": 3 }
    ]
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `userId` | number | Y | 사용자 ID |
| `periodStart` | string | Y | daily: 날짜, weekly: 주 시작일(월요일) |
| `metrics` | object | Y | 백엔드가 계산한 구조화 지표. 도메인별 shape는 자유 |
| `raw` | object | N | 리포트 서술에 참고할 원천/집계 데이터(세션 목록 등) |

#### Response 200

```json
{
  "domain": "sleep",
  "period": "weekly",
  "periodStart": "2026-06-29",
  "summary": "이번 주 평균 수면 점수는 74점이며, 실제 수면 시간은 평균 6시간 42분입니다.",
  "highlights": [
    "지난주보다 평균 수면 시간이 18분 줄었습니다.",
    "중간 각성이 3회 이상인 날이 2일 있었습니다."
  ],
  "recommendations": [
    "취침 1시간 전 조명을 낮추고 화면 사용을 줄여보세요.",
    "기상 시간을 일정하게 유지해 수면 리듬을 안정화해보세요."
  ],
  "sources": ["core-api"]
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `domain` | string | `sleep` \| `posture` |
| `period` | string | `daily` \| `weekly` |
| `periodStart` | string | 요청과 동일 |
| `summary` | string | 핵심 지표를 한눈에 볼 수 있는 문장형 요약 |
| `highlights` | array | 주요 변화, 위험 신호, 개선 포인트 |
| `recommendations` | array | 사용자가 바로 실행할 수 있는 권장 액션 |
| `sources` | array | 리포트 생성에 사용한 데이터 출처(`core-api`, 추가로 tool 호출 시 `rag` 등) |

동기 응답으로 설계했다(단순함 우선). 리포트 생성이 길어져 백엔드 타임아웃이 문제가 되면 `202 + jobId` 폴링 패턴으로 전환할 수 있으나, 현재 범위에서는 필요하지 않다.

> **백엔드 팀 설계와의 차이**: 백엔드 쪽 API 명세서에는 이와 별개로 `/sleep/v1/reports`·`/power/v1/reports`가 **비동기 job 패턴**(`202+jobId` → `GET /jobs/{jobId}` 폴링)으로, 응답도 `{ reportText, embedding, model, embeddingModel }` 형태(문자열 하나 + 임베딩)로 이미 설계되어 있다. 프론트가 `summary`/`highlights`/`recommendations`로 나뉜 구조를 기대하므로 **본 문서(§1.2)의 동기·구조화 계약을 확정안으로 유지**하기로 했고, 백엔드 팀에는 `/sleep/v1`·`/power/v1`의 job 패턴 대신 이 계약(`POST /reports/v1/{domain}/{period}`, 동기 응답)을 구현해달라고 별도로 요청해야 한다. `power` 도메인을 이 패턴에 포함할지도 함께 확인이 필요하다(현재 `domain`은 `sleep`\|`posture`만 정의됨).

#### Response 400

```json
{
  "error": {
    "code": "NO_DATA",
    "message": "raw.sessions 가 비어 있습니다. 해당 기간 데이터를 먼저 조회해 Body 를 구성하세요.",
    "field": "raw.sessions"
  }
}
```

### 1.3 LLM 포워딩 API

벡엔드 API 명세서에 이미 구체화된 계약을 그대로 채택한다. 백엔드가 챗 턴(§1.1) 이외의 용도(대시보드 문구 생성, 인사이트 문장화 등)로 LLM이 필요할 때 이 프록시를 거친다. **챗 턴의 LLM 호출은 에이전트가 직접 수행**하며 이 API와 무관하다.

```http
GET  /llm/v1/models
POST /llm/v1/chat/completions
POST /llm/v1/embeddings
```

- OpenAI Chat Completions / Embeddings 호환 스키마(`model`, `messages`, `stream` 등)를 그대로 따른다. 백엔드는 OpenAI SDK의 `base_url`을 `http://<agent>:8501/llm/v1`로 두고 사용할 수 있다.
- `GET /models`는 실제 서빙 가능한 모델 목록을 반환한다(`id`, `role: 'chat'|'embedding'`, `provider`, embedding이면 `dimension`).
- `POST /chat/completions`는 `stream=false`면 단일 JSON, `stream=true`면 SSE(`chat.completion.chunk`)로 응답한다.
- `POST /embeddings`는 스트리밍을 지원하지 않으며, 임베딩 모델 차원은 `vec_*` 스키마(현재 `nomic-embed-text`, 768차원)와 일치해야 한다.
- 채팅 히스토리는 이 API로 저장하지 않는다(`chat_history`는 백엔드 소유).
- 상세 요청/응답 예시·에러 코드(`MODEL_NOT_FOUND`, `LLM_PROVIDER_ERROR`, `LLM_TIMEOUT`)는 백엔드 API명세서의 "LLM 모델 포워딩 API" 절을 그대로 따른다.

---

## 2. 에이전트 → 백엔드 API

Agent Server 내부 tool은 아래 백엔드 API를 호출한다. 실제 구현 파일은 `app/tools/*_api.py`이며, `WAVEHOME_CORE_API_BASE_URL`(백엔드 :8500)을 기준으로 요청한다.

기본 경로 예시:

```text
http://127.0.0.1:8500/internal/v1
```

### 2.1 DB 조회

```http
POST /internal/v1/db/query
```

배치 조회다. 한 요청에 여러 테이블 조회를 `queries[]`로 묶어 보내고 `results[]`로 1:1 받는다. 채팅 중 원천 데이터가 필요할 때, 그리고 리포트 생성 중 인라인 데이터만으로 부족할 때 호출한다.

`queries[]` 최대 **10개**. 각 query의 `limit` 기본 **100**, 상한 **1000**. `filter`에 허용되지 않은 키·값이 있으면 해당 query만 `results[i].error`로 실패하고 나머지 query는 계속 처리한다(요청 전체가 실패하지 않음). `vec_*` 가상 테이블은 조회 대상이 아니다(벡터 검색은 §2.6 RAG 사용).

#### Request

```json
{
  "queries": [
    {
      "table": "sleep_stat",
      "filter": { "userId": 1, "granularity": "30m", "from": "2026-07-01 00:00:00", "to": "2026-07-02 00:00:00" },
      "limit": 48,
      "order": "asc"
    }
  ]
}
```

#### Response 200

```json
{
  "results": [
    {
      "table": "sleep_stat",
      "count": 48,
      "items": [
        { "id": 4120, "userId": 1, "timeStart": "2026-07-01 03:00:00", "hrMean": 62.0 }
      ]
    }
  ]
}
```

#### Response 200 — query 하나만 실패(나머지는 성공)

```json
{
  "results": [
    {
      "table": "sleep_stat",
      "count": 0,
      "items": [],
      "error": { "code": "INVALID_FILTER", "message": "userId 는 필수입니다.", "field": "userId" }
    }
  ]
}
```

#### 허용 테이블·필터

백엔드 API명세서에 이미 확정되어 있어 그대로 채택한다. 공통 키: `id`(PK exact match), `from`/`to`(시간축 있는 테이블에서 반열림 `[from, to)`).

| 테이블 | 필수 필터 | 그 외 허용 필터 | 시간축 · 기본 정렬 |
| --- | --- | --- | --- |
| `user` | — | `id` | 없음 · `id` asc |
| `room` | — | `id`, `userId`(`room_user_map` 조인) | 없음 · `id` asc |
| `room_user_map` | `roomId`\|`userId` 중 1개 | `roomId`, `userId` | 없음 |
| `device` | — | `id`, `class`, `archived`(기본 0), `roomId`(`device_room_map` 조인), `userId`(`device_user_map` 조인) | 없음 · `id` asc |
| `device_user_map` | `deviceId`\|`userId` 중 1개 | `deviceId`, `userId` | 없음 |
| `device_room_map` | `deviceId`\|`roomId` 중 1개 | `deviceId`, `roomId` | 없음 |
| `sleep_session` | `userId` | `id`, `roomId`, `nightDate`, `from`/`to` | `onset` · `nightDate` desc, `onset` desc |
| `sleep_stat` | `userId` | `id`, `sessionId`, `roomId`, `granularity`, `from`/`to` | `timeStart` · `timeStart` asc |
| `sleep_report` | `userId` | `id`, `period`, `periodStart`, `from`/`to` | `periodStart` · `periodStart` desc |
| `power_energy` | — | `deviceId`(생략=전체, `null`=합산행, 정수=해당 장치), `id`, `granularity`, `from`/`to`, `roomId`, `userId` | `timeStart` · `timeStart` asc |
| `power_report` | — | `deviceId`(위와 동일 규칙), `id`, `energyId`, `period`, `periodStart`, `from`/`to`, `roomId`, `userId` | `periodStart` · `periodStart` desc |
| `gesture_set` | — | `id`, `archived`(기본 0) | 없음 · `id` asc |
| `gesture_log` | — | `gestureSetId`, `radarId`, `deviceId`, `classId`, `from`/`to` | `timestamp` · `timestamp` desc |
| `routine_task` | `userId` | `id`, `category`, `dayOfWeek`, `done`, `createdBy` | 없음 · `dayOfWeek` asc, `startMinute` asc |
| `notification` | `userId` | `id`, `type`, `read`, `from`/`to` | `createdAt` · `createdAt` desc |
| `chat_history` | `userId` | `id`, `from`/`to` | `createdAt` · `createdAt` desc |
| `insight` | `userId` | `id`, `domain`, `period`, `approved`, `from`/`to` | `createdAt` · `createdAt` desc |

> **백엔드에 요청 필요한 2건**: (1) `device_control`이 이 표(원본은 백엔드 API명세서의 `DbTable` enum)에 없다. §2.3 기기 제어에서 제어 항목 목록을 조회하려면 추가가 필요하다. (2) `sleep_*`처럼 `posture_*` 계열 테이블이 전혀 없다 — §1.2의 `posture` 도메인 리포트를 만들려면 스키마 이관과 함께 이 표에도 추가해야 한다. `event`(§2.4 신설 제안)도 아직 이 표에 없다.

### 2.2 기기 조회

```http
GET /internal/v1/devices?roomId={roomId}&userId={userId}
```

`device_agent`가 사용자의 가전 제어 요청을 실행하기 전에 대상 기기와 현재 제어값을 확인하기 위해 호출한다. DB 스키마와 무관하게, 백엔드가 어떤 저장 방식을 쓰든 이 응답 shape만 지키면 된다.

`userId`는 필터가 아니라 권한 확인용이다. 기기는 `room`에 속하고 사용자는 `room_user_map`으로 방에 매핑되므로, 백엔드는 `roomId`+`userId`가 `room_user_map`에 존재하는지 먼저 확인한 뒤 해당 방의 기기 목록을 반환한다(매핑이 없으면 `404`). `roomId`만으로 조회하면 이 권한 확인이 빠지므로 두 파라미터를 함께 유지한다.

#### Response 200

```json
[
  {
    "id": 7714208883279181,
    "name": "거실 에어컨",
    "roomId": 2,
    "class": "tuya_ep2h",
    "controls": [
      { "id": 1, "label": "온도", "type": "number", "currentValue": 24, "min": 18, "max": 30, "unit": "C" }
    ]
  }
]
```

### 2.3 기기 제어

```http
POST /internal/v1/devices/{deviceId}/controls/{controlId}
```

에이전트가 자연어 요청을 구체적인 제어값으로 변환한 뒤 실행을 요청한다.

`{controlId}`는 기기 하나가 가질 수 있는 여러 제어 항목(온도, 전원, 모드 등) 중 하나를 가리키며, §2.2 응답의 `controls[].id`(백엔드 `device_control.id`)와 동일하다.

#### Request

```json
{
  "value": 23,
  "userId": 1,
  "reason": "사용자가 에어컨 온도를 조금 낮춰달라고 요청함"
}
```

#### Response 200

```json
{
  "status": "ok",
  "deviceId": 7714208883279181,
  "controlId": 1,
  "value": 23,
  "appliedAt": "2026-07-06 09:36:00"
}
```

### 2.4 일정 조회

```http
GET /internal/v1/users/{userId}/routine-tasks?dayOfWeek={dayOfWeek}&date={date}
```

`schedule_agent`가 일정 변경 요청을 해석하고 대상 일정을 찾기 위해 호출한다. 매주 반복되는 루틴(`routine_task`)과 특정 날짜에만 있는 1회성 일정(`event`)을 함께 조회한다.

- `dayOfWeek`만 주면 그 요일에 반복되는 루틴(`routine_task`)만 반환한다.
- `date`(`YYYY-MM-DD`)를 추가하면 그 날짜의 1회성 일정(`event`)도 함께 조회해 합쳐서 반환한다. 1회성 일정은 요일이 아니라 날짜로만 식별되므로 `date` 없이는 조회되지 않는다.
- 응답 항목마다 `type`(`routine` | `event`)으로 출처를 구분한다. `routine`은 `dayOfWeek`, `event`는 `date` 필드를 갖는다.

#### Response 200

```json
[
  {
    "id": 501,
    "type": "routine",
    "title": "운동",
    "dayOfWeek": "mon",
    "category": "exercise",
    "startMinute": 1260,
    "endMinute": 1290,
    "done": false
  },
  {
    "id": 12,
    "type": "event",
    "title": "병원 예약",
    "date": "2026-07-06",
    "category": "posture",
    "startMinute": 1140,
    "endMinute": 1170,
    "done": false
  }
]
```

### 2.5 일정 변경

```http
PATCH /internal/v1/routine-tasks/{taskId}
```

에이전트가 일정 변경 의도를 해석한 뒤 실행을 요청한다. DB 수정은 백엔드가 수행한다. `routine_task`와 `event`는 각각 별도 PK 시퀀스라 `taskId`만으로는 대상 테이블을 구분할 수 없으므로, §2.4 응답에서 받은 `type`을 그대로 함께 보낸다.

#### Request (반복 루틴 이동)

```json
{
  "type": "routine",
  "dayOfWeek": "tue",
  "startMinute": 1260,
  "endMinute": 1290,
  "reason": "사용자가 오늘 밤 운동 일정을 내일로 옮겨달라고 요청함"
}
```

#### Request (1회성 일정 이동)

```json
{
  "type": "event",
  "date": "2026-07-07",
  "startMinute": 1140,
  "endMinute": 1170,
  "reason": "사용자가 오늘 저녁 병원 예약을 내일로 옮겨달라고 요청함"
}
```

#### Response 200

```json
{
  "id": 501,
  "type": "routine",
  "status": "ok",
  "dayOfWeek": "tue",
  "startMinute": 1260,
  "endMinute": 1290,
  "updatedAt": "2026-07-06 09:35:00"
}
```

### 2.6 RAG 검색

채팅 기본 흐름의 필수 tool로 승격한다(§1.1 참고 — LLM이 필요하다고 판단하면 db.query와 마찬가지로 기본으로 호출 가능한 tool 목록에 포함). 백엔드 API명세서에 이미 구체화된 계약을 그대로 채택한다.

```http
POST /internal/v1/rag/search
```

RAG는 백엔드에서 처리한다(백엔드가 그 임베딩 벡터로 자기 SQLite 안의 sqlite-vec를 조회해 스니펫을 찾음). 에이전트는 벡터 인덱스·DB에 직접 접근하지 않고, 쿼리 텍스트와 검색 대상(`targets[]`)만 넘기면 백엔드가 쿼리를 임베딩(§1.3 `/llm/v1/embeddings`)하고 `sqlite-vec`로 유사 문서를 찾아 스니펫을 반환한다.

- 쿼리 임베딩은 1회만 수행하고 `targets[]`의 각 컬렉션 검색에 재사용한다.
- 컬렉션은 `sleep_report` | `sleep_stat` | `power_report` 3종뿐이다(`posture_*`는 스키마 이관 후 추가 필요 — §1.2 참고). raw 통계·인사이트 등은 벡터가 없어 RAG 대상이 아니다(§2.1 db.query 사용).
- 컬렉션마다 필터 축이 다르다: 수면 계열은 `userId`, 전력은 `deviceId`(생략=전체, `null`=합산). `userId`만 준 전력 검색은 백엔드가 `device_user_map`으로 사용자 소유 계측 장치를 해석한다.
- 요청 `targets[i]`와 응답 `results[i]`가 1:1 대응한다. `score`는 코사인 유사도(0~1, 1에 가까울수록 유사).

#### Request

```json
{
  "query": "요즘 잠을 잘 못 자는 것 같아",
  "targets": [
    { "collection": "sleep_report", "userId": 1, "period": "daily", "from": "2026-06-25", "to": "2026-07-04", "topK": 3 },
    { "collection": "sleep_stat", "userId": 1, "from": "2026-07-01 00:00:00", "to": "2026-07-04 12:00:00", "topK": 5 }
  ]
}
```

#### Response 200

```json
{
  "results": [
    {
      "collection": "sleep_report",
      "hits": [
        { "refId": 812, "score": 0.83, "text": "7월 1일 밤 수면은 총 5시간 36분으로 목표보다 30분 부족했습니다. ..." }
      ]
    },
    { "collection": "sleep_stat", "hits": [] }
  ]
}
```

턴 시작 전 백엔드가 미리 검색해 `context.retrieved`(§1.1)에 채워 넣는 **사전검색**도 가능하지만, 이는 지연시간 최적화용 옵션이고 정식 경로는 에이전트가 턴 중 이 tool로 직접 호출하는 것이다.

---

## 3. 리포트 생성 내용 기준

앱 화면에 표시할 리포트는 전달받은 지표(metrics)와 원천 데이터를 바탕으로 생성하며, 가능한 경우 아래 항목을 포함한다.

| 항목 | 설명 |
| --- | --- |
| 요약 | 핵심 지표를 한눈에 볼 수 있는 문장 |
| 주요 변화 | 이전 기간 대비 좋아지거나 나빠진 점 |
| 위험 신호 | 주의가 필요한 징후. 예: 잦은 각성, 수면 부족, 장시간 연속 착석 |
| 개선 포인트 | 사용자가 개선할 수 있는 구체적 지점 |
| 권장 액션 | 앱에서 보여줄 실천 가능한 행동 |

---

## 4. 에러 응답

백엔드-에이전트 양방향 모두 같은 에러 형식을 사용한다.

```json
{
  "error": {
    "code": "CORE_API_UNAVAILABLE",
    "message": "백엔드에서 수면 데이터를 가져오지 못했습니다.",
    "detail": { "endpoint": "/internal/v1/db/query" }
  }
}
```

권장 에러 코드:

| HTTP | code | 설명 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 필수 필드 누락 또는 잘못된 요청 |
| 404 | `NOT_FOUND` | 일정, 기기, 데이터 없음 |
| 409 | `CONFLICT` | 일정 충돌 또는 제어 상태 충돌 |
| 422 | `UNSUPPORTED_INTENT` | 실행할 수 없는 자연어 요청 |
| 502 | `CORE_API_UNAVAILABLE` | 백엔드 호출 실패 (에이전트 → 백엔드) |
| 502 | `LLM_PROVIDER_ERROR` | LLM 제공자 응답 실패 (백엔드 → 에이전트) |
| 504 | `CORE_API_TIMEOUT` | 백엔드 응답 시간 초과 |

부분 데이터만 조회된 경우에는 가능한 한 응답을 생성하되, `sources` 또는 답변 문장에 데이터 제한을 명시한다.

---

## 5. 구현 매핑

| 기능 | Agent Server 코드 | 호출하는 백엔드 API |
| --- | --- | --- |
| 채팅 전반 | `app/routers/chat.py`, `app/graph/` | `POST /internal/v1/db/query` |
| 기기 제어 | `device_agent`, `app/tools/device_api.py` | `GET /internal/v1/devices`, `POST /internal/v1/devices/{deviceId}/controls/{controlId}` |
| 일정 변경 | `schedule_agent`, `app/tools/schedule_api.py` | `GET /internal/v1/users/{userId}/routine-tasks`, `PATCH /internal/v1/routine-tasks/{taskId}` |
| 수면/자세 리포트 | `app/routers/reports.py`, `report_agent` | (인라인 데이터, 필요 시 `POST /internal/v1/db/query`) |

---

## 6. 테스트 시나리오

### 채팅

```bash
curl -X POST http://127.0.0.1:8501/chat/v1/turns \
  -H "Content-Type: application/json" \
  -d '{
    "chatHistoryId": 42,
    "userId": 1,
    "messages": [{"role": "user", "content": "어젯밤 수면 어땠어?"}],
    "context": {"now": "2026-07-06 09:30:00"},
    "stream": false
  }'
```

### 기기 제어

```bash
curl -X POST http://127.0.0.1:8501/chat/v1/turns \
  -H "Content-Type: application/json" \
  -d '{
    "chatHistoryId": 42,
    "userId": 1,
    "messages": [{"role": "user", "content": "에어컨 온도 조금 낮춰줘."}],
    "stream": false
  }'
```

### 리포트

```bash
curl -X POST http://127.0.0.1:8501/reports/v1/sleep/weekly \
  -H "Content-Type: application/json" \
  -d '{
    "userId": 1,
    "periodStart": "2026-06-29",
    "metrics": {"averageScore": 74, "avgSleepMinutes": 402},
    "raw": {"sessions": []}
  }'
```

## 7. TODO

- DB 스키마 설계 남은 것: `device_control`, `posture_*`, `event` 테이블을 허용 목록에 추가 요청(아래 항목과 연결).
- RAG 검색을 tool로 추가
- **백엔드 팀에 확인/요청 필요(teammate_api.md와의 차이)**:
  1. 리포트 생성 API를 백엔드 API 명세서의 `/sleep/v1`·`/power/v1` 비동기 job 패턴이 아니라 본 문서 §1.2(`POST /reports/v1/{domain}/{period}`, 동기 응답, `summary`/`highlights`/`recommendations` 구조)로 구현해달라고 요청. `power` 도메인도 이 패턴에 포함할지 확인.
  2. `posture` 도메인 스키마 이관(`db_past.md` → `db_updated.md`, 제안안은 `db_updated.md` "자세 트래킹" 절 참고) 및 §1.2 `posture` 리포트 구현 요청.
  3. `POST /internal/v1/devices/{deviceId}/controls/{controlId}` 등 §2.2~2.5(기기 제어·일정) 구현 — 백엔드 API 명세서에서 "에이전트 담당이 먼저 정리"로 남겨둔 부분이므로 본 문서 §2.2~2.5를 그대로 전달.
  4. `/internal/v1/db/query`의 `DbTable` 허용 목록에 `device_control`, `posture_*`, `event` 추가 요청.
- 추후 확장 고려 사항: **Agentic RAG (평가 후 재검색)**, 한 턴 안에서 `rag.search`를 여러 번 호출해도 된다 — 짧은 동기 tool 호출일 뿐이라 프로토콜상 제약이 없다. 권장 패턴: (1) 검색 → (2) LLM 또는 별도 grading 노드가 스니펫이 질문에 답하기 충분한지 평가 → (3) 부족하면 `query`를 재작성하거나 `targets[].from`/`to`/`topK`를 조정해 다시 호출 → (4) 충분해지면 최종 답변 생성. 챗 SSE 커넥션이 그동안 계속 열려 있으므로 같은 턴에 재검색은 최대 2~3회로 상한을 두는 것을 권장한다.