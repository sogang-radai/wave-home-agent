# WaveHome Agent Server

WaveHome의 AI 에이전트 서버입니다. 사용자 데이터, 센서 데이터, 일정, 기기 상태는 C++ 백엔드가 소유하고, Agent Server는 내부 API/tool을 통해 필요한 정보만 조회하거나 액션 실행을 요청합니다.

## 현재 역할

| 영역 | 엔드포인트 | 설명 |
| --- | --- | --- |
| 채팅 | `POST /chat/v1/turns` | LangGraph ReAct 루프로 필요한 tool을 선택하고 답변을 생성합니다. |
| 앱 리포트 | `POST /reports/v1/{domain}/{period}` | 앱 화면에 바로 표시할 `summary`/`highlights`/`recommendations`를 생성합니다. |
| LLM 프록시 | `/llm/v1/*` | 백엔드가 OpenAI 호환 방식으로 Ollama를 호출할 때 경유합니다. |
| 분석 job | `/sleep/v1/*`, `/power/v1/*` | RAG 코퍼스용 텍스트와 임베딩을 비동기로 생성합니다. |

자세, 관측, 생활 패턴용 레거시 agent 코드는 남아 있지만 현재 공개 라우트에는 연결되어 있지 않습니다. 실제 데이터가 연결된 경로는 수면, 전력, 일정, 기기 제어 중심입니다.

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
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_MS=20000

WAVEHOME_CORE_API_BASE_URL=http://127.0.0.1:9000
WAVEHOME_CORE_API_TIMEOUT_MS=5000
WAVEHOME_CORE_API_MOCK=true

WAVEHOME_AGENT_INTERNAL_BASE_URL=http://127.0.0.1:8500/internal/v1

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_MS=30000
DEFAULT_EMBEDDING_MODEL=nomic-embed-text
```

`WAVEHOME_CORE_API_MOCK=true`이면 C++ 백엔드가 없어도 mock 데이터로 채팅 tool을 실행할 수 있습니다. `/llm/v1/*`와 `embed:true` 분석 job은 `OLLAMA_BASE_URL`의 Ollama 서버가 필요합니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/README.md](docs/README.md) | 문서 읽는 순서와 보조 자료 안내 |
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
GET  /sleep/v1/jobs/{jobId}

POST /power/v1/reports
GET  /power/v1/jobs/{jobId}
```
