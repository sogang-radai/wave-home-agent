| 절 | 내용 |
| --- | --- |
| [2.1 DB 조회](#21-db-조회) | 채팅/리포트 중 필요한 원천 데이터 조회 |
| [2.2 기기 조회](#22-기기-조회) | 제어 전 대상 기기와 현재 제어값 확인 |
| [2.3 기기 제어](#23-기기-제어) | 자연어 요청을 구체 제어값으로 실행 |
| [2.4 일정 조회](#24-일정-조회) | 반복 루틴과 1회성 일정 조회 |
| [2.5 일정 변경](#25-일정-변경) | 루틴/이벤트 이동 또는 수정 |
| [2.6 RAG 검색](#26-rag-검색) | 백엔드 sqlite-vec 기반 스니펫 검색 |
| [3. 리포트 생성 내용 기준](#3-리포트-생성-내용-기준) | 앱 화면용 리포트 문장 구성 기준 |
| [4. 에러 응답](#4-에러-응답) | 공통 에러 형식과 권장 코드 |
| [5. 구현 매핑](#5-구현-매핑) | Agent Server 코드와 API 대응 |
| [6. 테스트 시나리오](#6-테스트-시나리오) | curl 기반 수동 검증 예시 |


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
| 400 | `INVALID_WINDOW` | §1.4 `window`/`target` 검증 실패 |
| 400 | `NO_SLEEP_DATA` | §1.4 `sessions`가 비어 있음 |
| 400 | `INVALID_WEEK_START` | §1.4 weekly `periodStart`가 월요일이 아님 |
| 409 | `JOB_ALREADY_RUNNING` | §1.4 동일 대상 job이 이미 진행 중(`error.detail.jobId`) |
| 404 | `JOB_NOT_FOUND` | §1.4 jobId 없음 또는 24시간 경과 |
| — | `GENERATION_FAILED`/`GENERATION_TIMEOUT` | §1.4 job 실행 중 임베딩 생성 실패(HTTP 상태 아님 — `GET .../jobs/{jobId}`의 `status:"failed"` 응답 안 `error.code`) |

부분 데이터만 조회된 경우에는 가능한 한 응답을 생성하되, `sources` 또는 답변 문장에 데이터 제한을 명시한다.

---

## 5. 구현 매핑

| 기능 | Agent Server 코드 | 호출하는 백엔드 API |
| --- | --- | --- |
| 채팅 전반 | `app/routers/chat.py`, `app/graph/turn_graph.py`, `app/graph/tool_loop.py` | `POST /internal/v1/db/query`, `POST /internal/v1/rag/search` |
| 기기 제어 | `app/graph/tools.py`(`make_list_devices_tool`/`make_control_device_tool`), `app/tools/devices_internal.py` | `GET /internal/v1/devices`, `POST /internal/v1/devices/{deviceId}/controls/{controlId}` |
| 일정 변경 | `app/graph/tools.py`(`make_get_routine_tasks_tool`/`make_update_routine_task_tool`), `app/tools/routine_tasks_internal.py` | `GET /internal/v1/users/{userId}/routine-tasks`, `PATCH /internal/v1/routine-tasks/{taskId}` |
| 수면/자세 리포트 | `app/routers/reports_turn.py`, `app/graph/report_turn_graph.py` | (인라인 데이터, 필요 시 `POST /internal/v1/db/query`/`POST /internal/v1/rag/search`) |
| LLM 포워딩 | `app/routers/llm.py`, `app/clients/ollama.py` | (백엔드 아님 — Ollama `/v1/*`로 포워딩) |
| 수면 분석(job) | `app/routers/sleep_analysis.py`, `app/services/sleep_analysis.py`, `app/services/jobs.py`, `app/services/embeddings.py` | (인라인 데이터 + Gemini 텍스트 생성 + Ollama `/v1/embeddings`. 백엔드 API 호출 없음) |
| 전력 분석(job) | `app/routers/power_analysis.py`, `app/services/power_analysis.py` | (위와 동일) |

> 위 코드는 전부 §2를 mock으로 구현한 상태다(백엔드 `/internal/v1/*`가 아직 없음). `sleep_agent`/`posture_agent`/`observation_agent`/`lifestyle_agent`(`app/agents/`)와 그 mock 데이터 소스(`app/tools/{sleep,posture,observation,schedule}_api.py`)는 옛 설계 기준 코드가 남아있으나 현재 어떤 라우트에도 연결되어 있지 않다. (수면/전력 분석 job은 §2 mock과 무관 — 백엔드 API를 호출하지 않고 요청 Body의 인라인 데이터만으로 생성한다.)

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

### 수면 요약 (job)

```bash
curl -X POST http://127.0.0.1:8501/sleep/v1/summaries \
  -H "Content-Type: application/json" \
  -d '{
    "window": {"id": 4123, "userId": 1, "roomId": 1, "granularity": "30m", "timeStart": "2026-07-01 02:00:00", "coverage": 0.98, "hrMean": 58.1},
    "embed": false
  }'
# => {"jobId": "job_...", "status": "queued"}

curl http://127.0.0.1:8501/sleep/v1/jobs/job_...
```

### 수면 리포트 (job)

```bash
curl -X POST http://127.0.0.1:8501/sleep/v1/reports \
  -H "Content-Type: application/json" \
  -d '{
    "userId": 1, "period": "daily", "periodStart": "2026-07-01",
    "metrics": {"asleepTotalS": 20160, "efficiency": 0.75},
    "sessions": [{"id": 88, "userId": 1, "roomId": 1, "radarId": 7714208883279181, "nightDate": "2026-07-01", "onset": "2026-07-01 00:35:00", "finalWake": "2026-07-01 07:55:00", "efficiency": 0.75}],
    "stats30m": [],
    "embed": false
  }'
```

### 전력 리포트 (job)

```bash
curl -X POST http://127.0.0.1:8501/power/v1/reports \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": null, "period": "24h", "periodStart": "2026-07-01",
    "metrics": {"energyWh": 3820.5, "peakW": 1180.4},
    "target": {"id": 20514, "deviceId": null, "granularity": "24h", "timeStart": "2026-07-01", "energyWh": 3820.5, "coverage": 0.98, "sampleCount": 288},
    "embed": false
  }'
```
