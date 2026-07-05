# AI Agent Server - State / Agent / Tool 인터페이스 명세 (Level 3)

# 1. Global State

모든 Graph는 동일한 AgentState를 공유한다.

```python
AgentState

user_id

session_id

request

intent

required_context

tool_results

health_insights

report

action_plan

action_result

response
```

---

# 2. Domain Insight

모든 Health Agent는 동일한 형식을 반환한다.

```python
Insight

domain

summary

risk_level

positive_points

negative_points

recommendations

confidence
```

예)

```python
{
    "domain": "sleep",
    "summary": "...",
    "risk_level": "medium",
    "recommendations": [...],
    "confidence": 0.92
}
```

---

# 3. Tool 인터페이스

모든 Tool은 다음 규칙을 따른다.

입력

* user_id
* optional parameter

출력

* JSON

예)

Sleep API

```python
get_sleep_summary(
    user_id,
    start_date,
    end_date
)
```

반환

```python
{
    "avg_sleep": ...,
    "score": ...,
    "deep_sleep": ...
}
```

---

# 4. Agent 인터페이스

모든 Agent는 동일한 인터페이스를 가진다.

입력

AgentState

출력

AgentState

Agent는 자신의 필드만 수정한다.

---

# 5. Sleep Agent

읽기

* Sleep API

쓰기

없음

출력

sleep_insight

---

# 6. Posture Agent

읽기

* Posture API

쓰기

없음

출력

posture_insight

---

# 7. Observation Agent

읽기

* Observation API

쓰기

없음

출력

observation_insight

---

# 8. Lifestyle Agent

읽기

* Schedule API
* Observation API
* Sleep API (필요 시)

출력

lifestyle_insight

---

# 9. Schedule Agent

읽기

* Schedule API

쓰기

* Update Schedule API

출력

action_result

---

# 10. Device Agent

읽기

* Device Status API

쓰기

* Device Control API

출력

action_result

---

# 11. Insight Synthesizer

입력

* Sleep Insight
* Posture Insight
* Observation Insight
* Lifestyle Insight

출력

Health Summary

역할

각 Agent의 결과를 종합하여 중복을 제거하고, 상충되는 내용이 있는 경우 우선순위를 조정한 뒤 하나의 통합 건강 인사이트를 생성한다.

---

# 12. Prompt 관리 원칙

Prompt는 Agent별로 독립 관리한다.

```
prompts/

sleep/

posture/

observation/

lifestyle/

report/

device/

schedule/

system/
```

Prompt 간 책임을 혼합하지 않는다.

---

# 13. Tool 계층 원칙

Agent는 Tool 구현을 알지 못한다.

```
Agent

↓

Tool

↓

REST / gRPC

↓

C++ Backend
```

HTTP 클라이언트, 인증, 재시도, 로깅은 Tool 계층의 책임이다.

---

# 14. 테스트 전략

각 계층을 독립적으로 검증한다.

* Tool 단위 테스트 (API Mock)
* Agent 단위 테스트 (LLM Stub/Mock)
* Graph 통합 테스트
* End-to-End 시나리오 테스트
* Prompt 회귀 테스트
* LangSmith 기반 실행 추적 및 평가

이를 통해 외부 API 변경, 프롬프트 수정, 그래프 변경이 서로에게 미치는 영향을 최소화한다.
