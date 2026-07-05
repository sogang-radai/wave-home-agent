from typing import Iterable

from app.models.insight import HealthSummary, Insight


_DOMAIN_LABELS = {
    "sleep": "수면",
    "posture": "자세",
    "observation": "생활 패턴",
    "lifestyle": "생활 습관",
}
_RISK_ORDER = {"unknown": -1, "low": 0, "medium": 1, "high": 2}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _overall_risk(insights: list[Insight]) -> str:
    known = [i.risk_level for i in insights if i.risk_level != "unknown"]
    if not known:
        return "unknown"
    return max(known, key=lambda level: _RISK_ORDER[level])


def _build_summary(insights: list[Insight], recommendations: list[str]) -> str:
    flagged = [i for i in insights if i.risk_level in ("medium", "high")]
    if not flagged:
        base = "전반적으로 안정적인 상태입니다."
    else:
        issues = [
            f"{_DOMAIN_LABELS.get(i.domain, i.domain)} 관련 {i.negative_points[0]}"
            if i.negative_points
            else f"{_DOMAIN_LABELS.get(i.domain, i.domain)} 이슈"
            for i in flagged
        ]
        base = f"최근 {', '.join(issues)}이(가) 확인됩니다."
    if recommendations:
        base += f" {recommendations[0]}을(를) 권장합니다."
    return base


def synthesize(insights: list[Insight]) -> HealthSummary:
    """Merges up to 4 domain Insights into one HealthSummary.

    This is deliberately rule-based, not a second LLM call: each Insight's
    summary is already LLM-authored prose, so this step is dedupe + priority
    ordering (interface.md #11), a mechanical aggregation task. A future LLM
    smoothing pass could be added here behind a settings flag if needed.
    """
    if not insights:
        return HealthSummary(summary="분석할 데이터가 없습니다.", risk_level="unknown", confidence=0.0)

    positive_points = _dedupe(
        f"[{_DOMAIN_LABELS.get(i.domain, i.domain)}] {point}"
        for i in insights
        for point in i.positive_points
    )
    negative_points = _dedupe(
        f"[{_DOMAIN_LABELS.get(i.domain, i.domain)}] {point}"
        for i in insights
        for point in i.negative_points
    )

    ranked = sorted(insights, key=lambda i: _RISK_ORDER[i.risk_level], reverse=True)
    recommendations = _dedupe(rec for i in ranked for rec in i.recommendations)[:5]

    confidence = sum(i.confidence for i in insights) / len(insights)

    return HealthSummary(
        summary=_build_summary(insights, recommendations),
        risk_level=_overall_risk(insights),
        highlights=(positive_points + negative_points)[:8],
        recommendations=recommendations,
        domains=insights,
        confidence=confidence,
    )
