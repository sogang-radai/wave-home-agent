# WaveHome Agent Server

WaveHome의 AI 에이전트 서버입니다. 사용자 데이터, 센서 데이터, 일정, 기기 상태는 C++ 백엔드가 소유하고, Agent Server는 내부 API/tool을 통해 필요한 정보만 조회하거나 액션 실행을 요청합니다.

## 현재 역할

| 영역 | 엔드포인트 | 설명 |
| --- | --- | --- |
| 채팅 | `POST /chat/v1/turns` | LangGraph ReAct 루프로 필요한 tool을 선택하고 답변을 생성합니다. |
| 앱 리포트 (레거시) | `POST /reports/v1/{domain}/{period}` | 앱 화면에 바로 표시할 `summary`/`highlights`/`recommendations`를 생성합니다. |
| LLM 프록시 | `/llm/v1/*` | 백엔드가 OpenAI 호환 방식으로 Ollama를 호출할 때 경유합니다. |
| 분석 job | `/sleep/v1/summaries`, `/sleep/v1/reports`, `/power/v1/*` | RAG 코퍼스용 텍스트와 임베딩을 비동기로 생성합니다. |
| 수면 계획 job | `POST /sleep/v1/plans` | 특정 밤의 취침/기상 시각·목표 수면 시간 등을 담은 계획을 생성합니다. |
| 인사이트 생성 job | `/insight/v1/*` | 대시보드 배너·주간계획·리포트용 인사이트를 배치 생성합니다. |
| 주간 계획 배너 job | `/weekly-plan/v1/*` | 주간 계획 화면 상단 배너 문구를 생성합니다. |
| 목표 코칭 job | `/goal-coaching/v1/*` | 사용자가 설정한 목표(수면/자세/멘탈/생활/식습관)에 대해 최근 30일 행동 데이터 기반 과거 요약·전망·추천(`action`/`tip`)을 생성합니다. |

기기 제어·룰·예약·일정·알람 tool(`app/tools/*_internal.py`)은 `agent-be/agent-api/*.md` 신규 스펙에 맞춰 구현돼 있고, 백엔드도 `/internal/v1/rules`·`/schedule-tasks`·`/alarms` 등 대응 엔드포인트를 구현했습니다. 다만 로컬 기본값은 여전히 `WAVEHOME_CORE_API_MOCK=true`(mock 데이터)입니다 — 실 백엔드로 검증하려면 `false`로 바꾸고 `WAVEHOME_CORE_API_BASE_URL`이 실행 중인 C++ 서버를 가리키는지 확인하세요.

## 실행

Python 3.12 권장:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8501
```

확인:

- API: `http://127.0.0.1:8501`
- Swagger: `http://127.0.0.1:8501/docs`
- Health check: `http://127.0.0.1:8501/health`
- Postman documentation: `https://documenter.getpostman.com/view/42800287/2sBY4JvhRh`

## 환경 변수

```env
LLM_PROVIDER=gemini

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_MS=20000

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-nano
OPENAI_TIMEOUT_MS=20000

WAVEHOME_CORE_API_BASE_URL=http://127.0.0.1:8500
WAVEHOME_CORE_API_TIMEOUT_MS=5000
WAVEHOME_CORE_API_MOCK=true
WAVEHOME_AGENT_INTERNAL_BASE_URL=http://127.0.0.1:8500/internal/v1

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_MS=30000
OLLAMA_CHAT_MODEL=gemma4:12b-mlx
OLLAMA_API_KEY=ollama
DEFAULT_EMBEDDING_MODEL=nomic-embed-text
```

`WAVEHOME_CORE_API_MOCK=true`이면 C++ 백엔드가 없어도 mock 데이터로 채팅 tool을 실행할 수 있습니다. `/llm/v1/*`와 `embed:true` 분석 job은 `OLLAMA_BASE_URL`의 Ollama 서버가 필요하고, `LLM_PROVIDER=ollama`일 때는 `OLLAMA_CHAT_MODEL`이 채팅 응답에도 쓰입니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/api.md](docs/api.md) | 백엔드-에이전트 API 계약의 전체 안내와 아키텍처 개요 |
| [docs/api1.md](docs/api1.md) | 백엔드가 Agent Server를 호출하는 인바운드 API |
| [docs/api2.md](docs/api2.md) | Agent Server가 백엔드를 호출하는 아웃바운드 API, 에러, 테스트 |
| [docs/agent_architecture.md](docs/agent_architecture.md) | 현재 LangGraph/서비스 런타임 구조 |
| [docs/design.md](docs/design.md) | 구현 배경, 아키텍처 원칙, 프로젝트 구조 |
| [docs/data_note.md](docs/data_note.md) | 에이전트가 기대하는 백엔드 데이터 영역 |
| [docs/todo.md](docs/todo.md) | 남은 작업을 한 곳에서 관리하는 TODO 목록 |

## 구현된 엔드포인트

```http
GET  /health

POST /chat/v1/turns
POST /reports/v1/{domain}/{period}

GET  /llm/v1/models
POST /llm/v1/chat/completions
POST /llm/v1/embeddings

POST /sleep/v1/summaries
POST /sleep/v1/reports
POST /sleep/v1/plans
GET  /sleep/v1/jobs/{jobId}

POST /power/v1/reports
GET  /power/v1/jobs/{jobId}

POST /insight/v1/insights
GET  /insight/v1/jobs/{jobId}

POST /weekly-plan/v1/reports
GET  /weekly-plan/v1/jobs/{jobId}

POST /goal-coaching/v1/reports
GET  /goal-coaching/v1/jobs/{jobId}
```
