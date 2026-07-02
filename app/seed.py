from __future__ import annotations

from sqlalchemy.orm import Session

from app.ids import new_id
from app.models import Account, SuggestionChip

_INSIGHT_SUGGESTIONS = [
    "오늘 수면 인사이트 알려줘",
    "자세 점수가 왜 낮아졌어?",
    "오늘 심박수 어때?",
]

_SUGGESTION_POOL = [
    {"icon": "🌙", "label": "수면 분석", "prompt": "어젯밤 수면 점수를 분석해줘"},
    {"icon": "🧘", "label": "자세 교정", "prompt": "거북목 개선 스트레칭 루틴 추천해줘"},
    {"icon": "❤️", "label": "심박 트렌드", "prompt": "오늘 심박수가 평소와 다른 이유가 뭐야?"},
    {"icon": "🏠", "label": "가전 자동화", "prompt": "취침 전 가전 자동화 설정 도와줘"},
    {"icon": "📋", "label": "헬스 루틴", "prompt": "이번 주 건강 목표를 세워줘"},
    {"icon": "💤", "label": "수면 환경", "prompt": "더 깊은 수면을 위한 실내 환경 알려줘"},
    {"icon": "🌡️", "label": "최적 온도", "prompt": "수면에 최적인 실내 온도가 몇 도야?"},
    {"icon": "⚡", "label": "에너지 향상", "prompt": "에너지 점수를 높이는 방법 알려줘"},
]


def seed_initial_data(db: Session) -> None:
    if db.query(Account).first() is None:
        db.add(Account(id=new_id("acc"), name="나"))

    if db.query(SuggestionChip).first() is None:
        seq = 0
        for prompt in _INSIGHT_SUGGESTIONS:
            seq += 1
            db.add(
                SuggestionChip(
                    id=new_id("sug"),
                    group="insight_suggestion",
                    icon=None,
                    label=prompt,
                    prompt=prompt,
                    seq=seq,
                )
            )
        seq = 0
        for item in _SUGGESTION_POOL:
            seq += 1
            db.add(
                SuggestionChip(
                    id=new_id("sug"),
                    group="suggestion_pool",
                    icon=item["icon"],
                    label=item["label"],
                    prompt=item["prompt"],
                    seq=seq,
                )
            )

    db.commit()
