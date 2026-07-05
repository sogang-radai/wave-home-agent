# AI Agent Server - LangGraph 상세 설계 (Level 2)

# 1. Graph 계층 구조

AI Agent Server는 하나의 거대한 LangGraph를 구성하지 않는다.

대신 역할별 Subgraph를 구성하고, 최상위 Supervisor Graph가 이를 오케스트레이션한다.

```text
SupervisorGraph
│
├── ChatGraph
│
├── ReportGraph
│
├── ActionGraph
│
└── HealthAnalysisGraph
```

각 Graph는 독립적으로 테스트 및 실행할 수 있으며, 필요에 따라 단독 API로도 노출 가능하도록 설계한다.

---

# 2. Supervisor Graph

## 역할

사용자 요청을 분석하여 적절한 하위 Graph로 라우팅한다.

## 입력

* User Request
* User ID

## 출력

* ChatGraph
* ReportGraph
* ActionGraph

## 노드 구성

```text
START

↓

Load User Context

↓

Intent Classification

↓

Route Graph

├── ChatGraph
├── ReportGraph
└── ActionGraph

↓

END
```

---

# 3. Chat Graph

## 역할

사용자와의 자연어 대화를 처리한다.

### 노드

```text
START

↓

Normalize Request

↓

Need Context?

↓

Collect Required Context

↓

Health Supervisor

↓

Merge Insights

↓

Generate Response

↓

Response Validation

↓

END
```

---

## Normalize Request

입력 문장을 정규화한다.

예)

"불 좀 꺼줘"

↓

"거실 조명을 꺼줘"

---

## Need Context

필요한 데이터 종류를 결정한다.

예)

질문

"어젯밤 잠 잘 잤어?"

필요

* Sleep Data

질문

"요즘 건강이 어때?"

필요

* Sleep
* Posture
* Observation
* Lifestyle

---

## Collect Required Context

Tool을 호출하여 필요한 데이터만 가져온다.

예)

* get_sleep_summary()
* get_posture_summary()
* get_observation_summary()

---

## Health Supervisor

분석이 필요한 Domain Agent를 선택한다.

예)

```text
Sleep

Posture

Observation
```

또는

```text
Sleep only
```

---

## Merge Insights

각 Agent 결과를 하나로 합친다.

입력

Sleep Insight

Posture Insight

Observation Insight

Lifestyle Insight

출력

Health Summary

---

## Generate Response

최종 사용자 응답 생성

LLM Prompt에는

* 사용자 질문
* Tool 결과
* Domain Insight

를 함께 제공한다.

---

## Response Validation

응답 품질 검사

검사 예

* 근거 없는 내용 포함 여부
* Tool 결과와 모순 여부
* 금지 표현 여부

---

# 4. Health Analysis Graph

Health 관련 질문에서만 실행된다.

```text
START

↓

Task Planning

↓

Parallel Execution

├── Sleep Agent
├── Posture Agent
├── Observation Agent
└── Lifestyle Agent

↓

Insight Synthesizer

↓

END
```

---

# 5. Report Graph

```text
START

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

Generate JSON

↓

END
```

---

# 6. Action Graph

```text
START

↓

Intent Analysis

↓

Action Planning

↓

Execute Tool

↓

Verify Result

↓

Generate Response

↓

END
```

---

# 7. Agent별 실행 방식

각 Domain Agent는 동일한 실행 패턴을 따른다.

```text
Receive State

↓

Call Tool

↓

Analyze

↓

Return Insight
```

---

# 8. 병렬 실행 전략

HealthAnalysisGraph에서는 Sleep, Posture, Observation, Lifestyle Agent를 동시에 실행한다.

각 Agent는 서로의 결과를 참조하지 않는다.

Insight Synthesizer에서만 결과를 통합한다.

---

# 9. 예외 처리

Tool 실패

↓

Retry

↓

Fallback

↓

사용자에게 제한사항 안내

LLM 실패

↓

Retry

↓

Fallback Prompt

↓

Error Response

---

# 10. 향후 추가 가능한 Graph

* Reflection Graph
* Recommendation Graph
* Notification Graph
* Personalization Graph
* Long-term Memory Graph
* Weekly Report Graph
* Monthly Report Graph
