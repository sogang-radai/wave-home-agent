from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PostureDailyReport, SleepDailyReport, SleepStageLog


def build_account_context(db: Session, account_id: str) -> str:
    lines: list[str] = []

    sleep_report = db.scalars(
        select(SleepDailyReport)
        .where(SleepDailyReport.account_id == account_id)
        .order_by(SleepDailyReport.date.desc())
    ).first()
    if sleep_report is not None:
        lines.append(
            f"- 최근 수면({sleep_report.date}): 점수 {sleep_report.score}점, "
            f"실제 수면 {sleep_report.actual_sleep_minutes}분, "
            f"{sleep_report.sleep_window_start:%H:%M}~{sleep_report.sleep_window_end:%H:%M} 취침"
        )

        heart_rates = db.scalars(
            select(SleepStageLog.heart_rate).where(SleepStageLog.report_id == sleep_report.id)
        ).all()
        if heart_rates:
            avg_heart_rate = round(sum(heart_rates) / len(heart_rates))
            lines.append(
                f"- 최근 수면 중 심박수: 평균 {avg_heart_rate}bpm "
                f"(최저 {min(heart_rates)}bpm, 최고 {max(heart_rates)}bpm)"
            )

    posture_report = db.scalars(
        select(PostureDailyReport)
        .where(PostureDailyReport.account_id == account_id)
        .order_by(PostureDailyReport.date.desc())
    ).first()
    if posture_report is not None:
        lines.append(
            f"- 최근 자세({posture_report.date}): 점수 {posture_report.score}점, "
            f"정자세 비율 {posture_report.correct_posture_percent}%, "
            f"거북목 감지 {posture_report.turtle_neck_count}회"
        )

    if not lines:
        return "아직 수집된 수면/자세 데이터가 없다."
    return "\n".join(lines)
