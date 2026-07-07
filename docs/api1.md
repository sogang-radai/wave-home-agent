이 문서는 백엔드가 Agent Server를 호출하는 인바운드 API 계약을 정의한다. 

| 절 | 내용 |
| --- | --- |
| [1.1 채팅](#11-채팅) | 대화 턴 실행, SSE 스트리밍, tool 진행 이벤트 |
| [1.2 인사이트 리포트](#12-인사이트-리포트) | 앱 화면용 수면/자세 리포트 생성 |
| [1.3 LLM 포워딩 API](#13-llm-포워딩-api) | 백엔드의 OpenAI 호환 LLM 프록시 |
| [1.4 Sleep/Power 분석 API](#14-sleeppower-분석-api-job-패턴) | RAG 코퍼스 적재용 비동기 분석 job |

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

> `posture`는 현재 백엔드 `DbTable` 목록과 에이전트 데이터 영역에 아직 없다. 백엔드에 자세 스키마와 이 리포트 API 구현을 별도로 요청해야 한다. 현재 누락 데이터는 [data_note.md](./data_note.md#아직-필요한-데이터), 관련 작업은 [todo.md](./todo.md#데이터스키마)를 참고한다.

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

백엔드 API 명세서에 이미 구체화된 계약을 그대로 채택한다. 백엔드가 챗 턴(§1.1) 이외의 용도(대시보드 문구 생성, 인사이트 문장화 등)로 LLM이 필요할 때 이 프록시를 거친다. **챗 턴의 LLM 호출은 에이전트가 직접 수행**하며 이 API와 무관하다.

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

### 1.4 Sleep/Power 분석 API (job 패턴)

Sleep/Power Analysis API는 RAG 코퍼스 생성을 위한 별도 job 계약으로 구현한다. §1.2(`POST /reports/v1/{domain}/{period}`)와는 **목적이 다르다**:

| | §1.2 인사이트 리포트 | §1.4 Sleep/Power 분석 API |
| --- | --- | --- |
| 목적 | 앱 화면에 바로 표시할 구조화된 리포트 | `sleep_stat.summary_text`/`sleep_report.report_text`/`power_report.report_text`와 `vec_*` 임베딩으로 DB에 적재해 나중에 RAG(§2.6)로 검색될 원본 텍스트 생성 |
| 응답 형태 | 동기, `summary`/`highlights`/`recommendations` 구조 | 비동기(job), `summaryText`/`reportText` 문자열 하나 + `embedding` |
| 호출 시점 | 사용자가 앱에서 리포트를 열람할 때 | 원본 데이터(30m 통계, 일/주간 세션, 전력 구간)가 새로 생기거나 백필될 때 |

두 계약은 서로 대체 관계가 아니라 **같은 원본 데이터를 두 가지 용도로 소비**한다 — §1.2는 그때그때 화면에 보여줄 문장을, §1.4는 나중에 검색될 코퍼스를 만든다.

#### 공통

- Base URL: `/sleep/v1`, `/power/v1` (에이전트 서버)
- 생성은 즉시 끝나지 않을 수 있어 **비동기 job**으로 처리한다. `POST`는 즉시 `202` + `jobId`를 반환하고, `GET .../jobs/{jobId}`로 폴링해 완료 시 결과를 받는다(SSE 미사용).
- **중복 요청**: 동일 대상(요약=`window.id`, sleep 리포트=`userId`+`period`+`periodStart`, power 리포트=`target.id`)에 `queued`/`running` job이 있으면 `POST`는 **409** `JOB_ALREADY_RUNNING`(`error.detail.jobId`에 기존 jobId).
- **jobId 보존**: `done`/`failed` 후 **24시간**(서버 프로세스 메모리 기준 — 재시작하면 즉시 유실됨, 관련 작업은 [todo.md](./todo.md#리포트분석) 참고) 동안 `GET .../jobs/{jobId}` 조회 가능. 이후 `404` `JOB_NOT_FOUND`.
- **POST vs job 실패**: 입력 검증(빈 `sessions`, 잘못된 `window`/`target.granularity` 등)은 **POST 400**. 텍스트 생성은 Gemini 키가 없거나 실패해도 rule-based 폴백으로 항상 성공하므로 실패하지 않는다. 임베딩(`embed:true`) 생성이 실패(Ollama 연결 불가/타임아웃)하면 폴백이 없으므로 job이 `failed`(`GENERATION_FAILED`/`GENERATION_TIMEOUT`)로 끝난다 — 로컬에 Ollama가 없다면 `embed:false`로 호출해 이 경로를 피할 수 있다.
- `model`/`embeddingModel`(옵션): 요청 시 힌트로 쓰이고, 응답의 `model`은 실제 사용된 모델명 또는(폴백 시) `"rule-based"`, `embeddingModel`은 실제 임베딩 모델명(기본 `nomic-embed-text`)이다.
- `/sleep/v1/jobs/{jobId}`는 그 경로에서 생성된 job(요약·수면 리포트)만 조회된다. `/power/v1/jobs/{jobId}`도 마찬가지로 전력 리포트 job만 조회되며, 다른 도메인의 jobId를 넣으면 `404`가 된다(도메인 간 안전장치).
- 공통 에러 응답: `{ "error": { "code": "...", "message": "..." } }`

#### POST `/sleep/v1/summaries`

30분(`sleep_stat.granularity='30m'`) 구간의 자연어 요약을 생성한다. `window`(대상 30m 행)를 인라인 전달, 더 정밀한 서술이 필요하면 `minutes`(1m 행)를 함께 실을 수 있다.

```json
{
  "window": { "id": 4123, "userId": 1, "roomId": 1, "sessionId": 88, "granularity": "30m", "timeStart": "2026-07-01 02:00:00", "timeEnd": "2026-07-01 02:30:00", "coverage": 0.98, "stageLabel": "deep", "hrMean": 58.1, "snoreRatio": 0.03 },
  "embed": true
}
```

**Response 202**: `{ "jobId": "job_...", "status": "queued" }`

**Response 400** — `window.granularity != "30m"`:

```json
{ "error": { "code": "INVALID_WINDOW", "message": "window.granularity 는 30m 이어야 합니다.", "field": "window.granularity" } }
```

완료 시 `GET /sleep/v1/jobs/{jobId}`의 `result`:

```json
{ "statId": 4123, "summaryText": "...", "embedding": [0.01, -0.02], "model": "gemini-3.1-flash-lite", "embeddingModel": "nomic-embed-text" }
```

#### POST `/sleep/v1/reports`

일간/주간 수면 리포트를 생성한다. `period`·`periodStart`·`metrics`(백엔드 계산)·`sessions`·`stats30m`을 인라인 전달한다.

**Response 400** — `sessions`가 빈 배열:

```json
{ "error": { "code": "NO_SLEEP_DATA", "message": "sessions 가 비어 있습니다. 해당 기간 수면 데이터를 먼저 조회해 Body 를 구성하세요.", "field": "sessions" } }
```

**Response 400** — `period="weekly"`인데 `periodStart`가 월요일이 아님:

```json
{ "error": { "code": "INVALID_WEEK_START", "message": "weekStart는 해당 주의 월요일 날짜여야 합니다.", "field": "periodStart" } }
```

완료 시 `result`: `{ "period": "daily", "periodStart": "2026-07-01", "reportText": "...", "embedding": [...], "model": "...", "embeddingModel": "..." }`

#### POST `/power/v1/reports`

전력 리포트(`1h`\|`24h`\|`1w`\|`1mo`)를 생성한다. `metrics`·`target`(대상 `power_energy` 행)·`children`(하위 구간, 옵션)을 인라인 전달한다. `deviceId: null`이면 계측 플러그 합산 리포트다.

**Response 400** — `target.granularity`가 `period`와 다름:

```json
{ "error": { "code": "INVALID_REQUEST", "message": "target.granularity 는 리포트 대상(1h/24h/1w/1mo)이어야 합니다.", "field": "target.granularity" } }
```

완료 시 `result`: `{ "energyId": 20514, "period": "24h", "periodStart": "2026-07-01", "deviceId": null, "reportText": "...", "embedding": [...], "model": "...", "embeddingModel": "..." }`

#### GET `/sleep/v1/jobs/{jobId}` · `/power/v1/jobs/{jobId}`

**Response 200** — 진행 중: `{ "jobId": "job_...", "status": "running" }` (`result`/`error` 키 없음)

**Response 200** — 완료: `{ "jobId": "job_...", "status": "done", "result": { ... } }`

**Response 200** — 실패: `{ "jobId": "job_...", "status": "failed", "error": { "code": "GENERATION_FAILED", "message": "..." } }`

**Response 404**: `{ "error": { "code": "JOB_NOT_FOUND", "message": "jobId 에 해당하는 작업이 없습니다." } }`

#### 전체 엔드포인트 요약

```http
POST /sleep/v1/summaries
POST /sleep/v1/reports
GET  /sleep/v1/jobs/{jobId}
POST /power/v1/reports
GET  /power/v1/jobs/{jobId}
```

#### 백엔드 연동 지점

- 30m `sleep_stat` 행이 생긴 뒤 `/summaries`를 호출해 `result.summaryText`/`result.embedding`을 `sleep_stat.summary_text`/`vec_sleep_stat`에 저장한다.
- 일/주간 리포트, 전력 리포트도 각각 완료 후 `sleep_report`/`power_report`와 그 `vec_*`에 upsert한다.
- 코드: `app/routers/sleep_analysis.py`·`power_analysis.py`, `app/services/sleep_analysis.py`·`power_analysis.py`·`jobs.py`·`embeddings.py`.

---

다음: [api2.md - 2. 에이전트 → 백엔드 API](./api2.md)
