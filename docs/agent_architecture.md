# AI Agent Server 아키텍처 설계

## 1. 개요

AI Agent Server는 LangGraph 기반의 AI 추론 서버로, 일반적인 백엔드 서버처럼 데이터베이스를 직접 관리하지 않는다.

사용자의 수면, 자세, 카메라 기반 관측 데이터, 일정, 가전 상태 등 모든 원천 데이터는 C++ Backend Server가 관리하며, AI Agent Server는 C++ 서버가 제공하는 API(Tool)를 통해 필요한 데이터만 조회하거나 액션을 요청한다.

AI Agent Server의 역할은 다양한 데이터를 종합적으로 해석하여 자연스러운 대화, 건강 인사이트, 리포트, 권장 행동, 일정 변경 및 가전 제어 의도를 생성하는 것이다.

---

# 2. 전체 시스템 구조

```
                    Frontend
                        │
                        │
                C++ Backend Server
      (Database / Sensor / Camera / Device)
                        │
          REST API / gRPC / Internal API
                        │
────────────────────────────────────────────
                 AI Agent Server
                 (LangGraph)
────────────────────────────────────────────
                        │
             Multi-Agent Orchestration
                        │
                 LLM + Tool Calling
```

### 역할 분리

### C++ Backend Server

* 사용자 데이터 저장
* 센서 데이터 관리
* 카메라 이벤트 관리
* 수면 데이터 관리
* 자세 데이터 관리
* 일정 관리
* 가전 제어
* 인증 및 권한 관리

### AI Agent Server

* 자연어 이해
* 의도 분석
* 필요한 컨텍스트 판단
* Tool(API) 호출
* 건강 데이터 해석
* 리포트 생성
* 액션 의도 생성
* 최종 응답 생성

AI Agent Server는 데이터베이스를 직접 조회하거나 수정하지 않으며, 모든 읽기와 쓰기는 C++ Backend Server의 API를 통해 수행한다.

---

# 3. 설계 원칙

## Domain-Driven Agent

기능별 전문 Agent를 분리한다.

예시

* Sleep Agent
* Posture Agent
* Observation Agent
* Lifestyle Agent
* Report Agent
* Device Agent
* Schedule Agent

각 Agent는 자신의 도메인만 이해하고 처리한다.

---

## Supervisor 기반 오케스트레이션

상위 Supervisor가 사용자 요청을 분석한 뒤 필요한 Agent만 선택하여 실행한다.

단일 LLM이 모든 작업을 수행하지 않고, 전문 Agent들의 분석 결과를 종합하여 최종 응답을 생성한다.

---

## Tool First Architecture

모든 외부 데이터 접근은 Tool을 통해 수행한다.

예시

* get_sleep_data()
* get_posture_data()
* get_camera_events()
* get_schedule()
* update_schedule()
* control_device()

Agent는 Tool만 호출하며 데이터 저장소의 구현 방식은 알지 못한다.

---

## Read / Write 분리

읽기 작업과 쓰기 작업을 명확히 분리한다.

### Read

* 데이터 조회
* 건강 분석
* 리포트 생성
* 인사이트 생성

### Write

* 일정 변경
* 가전 제어
* 사용자 설정 변경

Write 작업은 Action Agent를 통해 수행하며, 필요 시 사용자 확인 및 실행 결과 검증을 수행한다.

---

# 4. 멀티 에이전트 구조

```
                    START
                       │
                       ▼
             Conversation Router
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
 Chat Graph      Report Graph      Action Graph
        │
        ▼
 Health Supervisor
        │
 ┌──────┼──────────┬────────────┐
 ▼      ▼          ▼            ▼
Sleep  Posture Observation Lifestyle
Agent   Agent      Agent      Agent
 └──────┴──────────┴────────────┘
               │
               ▼
      Insight Synthesizer
               │
               ▼
      Response Generator
               │
               ▼
               END
```

---

# 5. Chat Graph

채팅은 가장 복잡한 그래프이며 여러 Agent를 동시에 사용할 수 있다.

```
START

↓

Intent Classification

↓

Need Context?

↓

Health Supervisor

↓

Parallel Execution

├── Sleep Agent
├── Posture Agent
├── Observation Agent
├── Lifestyle Agent
├── Schedule Agent (Optional)
├── Device Agent (Optional)

↓

Merge Results

↓

LLM Response

↓

END
```

Health 관련 질문이라면 여러 Agent가 병렬 실행되어 각각의 분석 결과를 생성한다.

예를 들어

사용자

> 지난주 건강 상태 어땠어?

병렬 수행

Sleep Agent

* 지난주 수면 분석

Posture Agent

* 지난주 자세 분석

Observation Agent

* 생활 패턴 분석

Lifestyle Agent

* 운동 및 생활 습관 분석

Insight Synthesizer가 각 분석 결과를 통합하여 하나의 종합 건강 의견을 생성한다.

---

# 6. Report Graph

리포트는 채팅과 별도의 그래프로 구현한다.

```
Report Request

↓

Report Type

↓

Collect Data

↓

Sleep Summary

↓

Posture Summary

↓

Observation Summary

↓

Trend Analysis

↓

Recommendation

↓

Report JSON

↓

END
```

리포트는 정형화된 결과를 생성하므로 Chat Graph와 독립적으로 관리한다.

지원 대상

* 어젯밤 수면 리포트
* 이번 주 수면 리포트
* 오늘 자세 리포트
* 이번 주 자세 리포트

---

# 7. Action Graph

쓰기 작업을 별도의 그래프로 분리한다.

```
User Request

↓

Intent Analysis

↓

Action Validation

↓

Schedule Agent
or
Device Agent

↓

Tool Execute

↓

Execution Verify

↓

Response
```

예시

"밤 11시에 불 꺼줘"

↓

Device Agent

↓

control_device()

↓

실행 결과 확인

↓

사용자 응답

---

# 8. Health Supervisor

Health Supervisor는 건강 관련 질문에서 어떤 Domain Agent를 실행할지 결정한다.

예시

"요즘 건강 어때?"

↓

Sleep Agent

↓

Posture Agent

↓

Observation Agent

↓

Lifestyle Agent

↓

Insight Synthesizer

↓

최종 건강 분석

---

# 9. Domain Agent 책임

## Sleep Agent

조회

* 수면 기록
* 수면 점수
* 깊은 수면
* REM
* 기상 시간

생성

* 수면 인사이트
* 위험 신호
* 개선 제안

---

## Posture Agent

조회

* 자세 이벤트
* 장시간 앉음
* 거북목
* 허리 자세

생성

* 자세 평가
* 개선 포인트

---

## Observation Agent

조회

* 카메라 이벤트
* 활동량
* 생활 패턴
* 야간 행동

생성

* 생활 인사이트

---

## Lifestyle Agent

조회

* 운동
* 일정
* 생활 습관

생성

* 습관 분석
* 건강 조언

---

## Schedule Agent

조회

* 일정

실행

* 일정 변경
* 일정 생성
* 일정 삭제

---

## Device Agent

조회

* 가전 상태

실행

* 가전 제어

---

# 10. Insight Synthesizer

Health Agent들의 분석 결과를 하나의 건강 의견으로 통합한다.

예시 입력

Sleep

* 평균 수면 감소

Posture

* 거북목 증가

Observation

* 활동량 감소

Lifestyle

* 운동 감소

최종 출력

"지난주는 수면 부족과 활동량 감소가 동시에 나타났으며, 장시간 앉아있는 시간이 증가했습니다. 이번 주에는 수면 시간을 확보하고 1시간마다 스트레칭을 권장합니다."

---

# 11. State 설계

```
AgentState

user_id

request

intent

context

tool_results

sleep_insight

posture_insight

observation_insight

lifestyle_insight

report

action_requests

final_response
```

각 Agent는 자신의 State만 수정하도록 설계한다.

---

# 12. Tool 계층

Tool은 C++ Backend API를 호출하는 역할만 수행한다.

```
tools/

sleep_api.py

posture_api.py

observation_api.py

schedule_api.py

device_api.py

report_api.py
```

Agent는 Tool만 호출하며 HTTP, gRPC 등의 통신 방식은 Tool 내부에 캡슐화한다.

---

# 13. 확장 전략

새로운 기능은 기존 그래프를 수정하기보다 새로운 Domain Agent를 추가하는 방식으로 확장한다.

예시

* Nutrition Agent
* Exercise Agent
* Heart Rate Agent
* Stress Agent
* Medication Agent
* Wearable Agent

Health Supervisor는 새로운 Agent를 연결만 하면 되므로 기존 구조를 크게 변경하지 않아도 된다.

---

# 14. 권장 프로젝트 구조

```
app/
├── graph/
│   ├── supervisor_graph.py
│   ├── chat_graph.py
│   ├── report_graph.py
│   ├── action_graph.py
│   └── health_graph.py
│
├── agents/
│   ├── sleep_agent.py
│   ├── posture_agent.py
│   ├── observation_agent.py
│   ├── lifestyle_agent.py
│   ├── schedule_agent.py
│   ├── device_agent.py
│   └── report_agent.py
│
├── tools/
│   ├── sleep_api.py
│   ├── posture_api.py
│   ├── observation_api.py
│   ├── schedule_api.py
│   ├── device_api.py
│   └── report_api.py
│
├── state/
│   └── agent_state.py
│
├── prompts/
│
├── services/
│
├── models/
│
└── main.py
```

---

# 15. 향후 발전 방향

초기 구현은 채팅, 리포트, 일정, 가전 제어를 중심으로 시작한다.

이후에는 다음과 같은 방향으로 확장할 수 있다.

* Domain Agent 추가를 통한 건강 분석 범위 확대
* 사용자 프로필과 장기 추세를 활용한 개인화 강화
* Reflection 및 Self-Review 노드를 통한 응답 품질 향상
* Human-in-the-Loop를 통한 중요 액션 승인
* LangGraph Checkpoint와 Memory를 활용한 대화 연속성 확보
* LangSmith 기반의 추적, 모니터링 및 평가 체계 구축

이러한 계층형 구조를 유지하면 새로운 기능을 추가하더라도 기존 그래프를 크게 변경하지 않고 확장할 수 있으며, 각 Agent의 책임이 명확하게 분리되어 유지보수성과 테스트 용이성을 확보할 수 있다.
