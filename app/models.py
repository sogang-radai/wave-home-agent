from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


SqliteBigInt = BigInteger().with_variant(Integer, "sqlite")


class Account(Base):
    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class BrowserSession(Base):
    __tablename__ = "session"

    sid: Mapped[str] = mapped_column(String(64), primary_key=True)
    active_account_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("account.id"), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class Room(Base):
    __tablename__ = "room"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class Device(Base):
    __tablename__ = "device"
    __table_args__ = (
        CheckConstraint(
            "class IN ('srs_r4sn', 'wave_mic', 'wave_cam', 'ir_reciever', "
            "'ir_remote', 'tizen_tv', 'tuya_ep2h', 'tuya_blind', 'hue_light')",
            name="ck_device_class",
        ),
        CheckConstraint(
            "direction IN ('input', 'output')",
            name="ck_device_direction",
        ),
        Index("idx_device_room_id", "room_id"),
        Index("idx_device_class", "class"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(30), ForeignKey("room.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    class_: Mapped[str] = mapped_column("class", String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    interface: Mapped[dict] = mapped_column(JSON, nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSON)


class DeviceControl(Base):
    __tablename__ = "device_control"
    __table_args__ = (UniqueConstraint("device_id", "label", name="uq_device_control_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(16), ForeignKey("device.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(30), nullable=False)
    hint: Mapped[str] = mapped_column(String(100), nullable=False)


class DeviceStatus(Base):
    __tablename__ = "device_status"
    __table_args__ = (
        CheckConstraint("connection IN ('online', 'idle')", name="ck_device_status_connection"),
    )

    device_id: Mapped[str] = mapped_column(String(16), ForeignKey("device.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    connection: Mapped[str] = mapped_column(String(10), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class GestureSet(Base):
    __tablename__ = "gesture_set"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class Gesture(Base):
    __tablename__ = "gesture"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    gesture_set_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("gesture_set.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)


class GestureRadarAssignment(Base):
    __tablename__ = "gesture_radar_assignment"

    gesture_id: Mapped[str] = mapped_column(String(20), ForeignKey("gesture.id"), primary_key=True)
    radar_device_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("device.id"), primary_key=True
    )


class GestureHistory(Base):
    __tablename__ = "gesture_history"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_gesture_history_confidence"),
        Index("idx_gesture_history_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    gesture_id: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("gesture.id"))
    gesture_name_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    device_id: Mapped[str] = mapped_column(String(16), ForeignKey("device.id"), nullable=False)
    device_name_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    radar_device_id: Mapped[str] = mapped_column(String(16), ForeignKey("device.id"), nullable=False)
    action_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class DeviceBinding(Base):
    __tablename__ = "device_binding"

    control_id: Mapped[int] = mapped_column(Integer, ForeignKey("device_control.id"), primary_key=True)
    gesture_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("gesture.id"), nullable=False, unique=True
    )


class SmartPlug(Base):
    __tablename__ = "smart_plug"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(16), ForeignKey("device.id"))
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    power_w: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    voltage_v: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    current_ma: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    switch_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hourly_cost_won: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    measured_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class PowerTrendPoint(Base):
    __tablename__ = "power_trend_point"
    __table_args__ = (
        CheckConstraint(
            "granularity IN ('hour', 'day', 'week', 'month')",
            name="ck_power_trend_granularity",
        ),
        UniqueConstraint("plug_id", "granularity", "seq", name="uq_power_trend_point"),
        Index("idx_power_trend_plug_granularity", "plug_id", "granularity", "seq"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    plug_id: Mapped[str] = mapped_column(String(16), ForeignKey("smart_plug.id"), nullable=False)
    granularity: Mapped[str] = mapped_column(String(10), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)


class Sound(Base):
    __tablename__ = "sound"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class TtsSpeaker(Base):
    __tablename__ = "tts_speaker"
    __table_args__ = (
        CheckConstraint("gender IN ('male', 'female')", name="ck_tts_speaker_gender"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(100), nullable=False)
    character: Mapped[str] = mapped_column(String(20), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)


class SleepConfig(Base):
    __tablename__ = "sleep_config"
    __table_args__ = (
        CheckConstraint("ac_temp BETWEEN 20 AND 28", name="ck_sleep_config_ac_temp"),
        CheckConstraint(
            "dim_start_minutes BETWEEN 10 AND 60",
            name="ck_sleep_config_dim_start_minutes",
        ),
        CheckConstraint(
            "final_brightness BETWEEN 0 AND 30",
            name="ck_sleep_config_final_brightness",
        ),
    )

    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), primary_key=True)
    bedtime: Mapped[Time] = mapped_column(Time, nullable=False)
    wake_time: Mapped[Time] = mapped_column(Time, nullable=False)
    wake_up_sound_id: Mapped[str] = mapped_column(String(50), ForeignKey("sound.id"), nullable=False)
    ac_auto: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ac_temp: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    light_auto: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dim_start_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    final_brightness: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    wake_light_ramp: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wake_music: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wake_tv_or_alarm: Mapped[bool] = mapped_column(Boolean, nullable=False)


class GeneralSetting(Base):
    __tablename__ = "general_setting"
    __table_args__ = (
        CheckConstraint("theme IN ('light', 'dark')", name="ck_general_setting_theme"),
    )

    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    notification_sound_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sound.id"), nullable=False
    )
    tts_speaker_id: Mapped[int] = mapped_column(Integer, ForeignKey("tts_speaker.id"), nullable=False)


class PostureAlertSetting(Base):
    __tablename__ = "posture_alert_setting"

    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), primary_key=True)
    turtle_neck: Mapped[bool] = mapped_column(Boolean, nullable=False)
    waist_tilt: Mapped[bool] = mapped_column(Boolean, nullable=False)
    long_sitting: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(
            "type IN ('timer', 'sleep', 'posture', 'temperature')",
            name="ck_notification_type",
        ),
        Index("idx_notification_account_created", "account_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SleepDailyReport(Base):
    __tablename__ = "sleep_daily_report"
    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uq_sleep_daily_report_date"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sleep_window_start: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    sleep_window_end: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    time_in_bed_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_sleep_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class SleepScoreFactor(Base):
    __tablename__ = "sleep_score_factor"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(50), nullable=False)
    tag: Mapped[str] = mapped_column(String(20), nullable=False)
    tone: Mapped[str] = mapped_column(String(10), nullable=False)


class SleepStageBreakdown(Base):
    __tablename__ = "sleep_stage_breakdown"
    __table_args__ = (
        CheckConstraint("stage IN ('awake', 'rem', 'light', 'deep')", name="ck_sleep_stage_breakdown_stage"),
        UniqueConstraint("report_id", "stage", name="uq_sleep_stage_breakdown_stage"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_text: Mapped[str] = mapped_column(String(20), nullable=False)
    tone: Mapped[str] = mapped_column(String(10), nullable=False)
    typical_percent_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    typical_percent_max: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class SleepHypnogramSegment(Base):
    __tablename__ = "sleep_hypnogram_segment"
    __table_args__ = (
        CheckConstraint("stage IN ('awake', 'light', 'deep', 'rem')", name="ck_sleep_hypnogram_stage"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class SleepMovementLevel(Base):
    __tablename__ = "sleep_movement_level"
    __table_args__ = (
        CheckConstraint("level BETWEEN 0 AND 100", name="ck_sleep_movement_level"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class SleepStageLog(Base):
    __tablename__ = "sleep_stage_log"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    time: Mapped[str] = mapped_column(String(5), nullable=False)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    stage_label: Mapped[str] = mapped_column(String(20), nullable=False)
    breath_rate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    heart_rate: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class SnoringEpisode(Base):
    __tablename__ = "snoring_episode"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_daily_report.id"), nullable=False)
    time: Mapped[str] = mapped_column(String(5), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class SleepWeeklyReport(Base):
    __tablename__ = "sleep_weekly_report"
    __table_args__ = (
        UniqueConstraint("account_id", "week_start", name="uq_sleep_weekly_report_start"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    week_start: Mapped[Date] = mapped_column(Date, nullable=False)
    week_end: Mapped[Date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    average_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class SleepWeeklyTrendPoint(Base):
    __tablename__ = "sleep_weekly_trend_point"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("sleep_weekly_report.id"), nullable=False)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    day: Mapped[str] = mapped_column(String(5), nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PostureDailyReport(Base):
    __tablename__ = "posture_daily_report"
    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uq_posture_daily_report_date"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(200))
    correct_posture_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    correct_posture_goal_percent: Mapped[Optional[int]] = mapped_column(SmallInteger)
    alert_accept_rate_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    total_sitting_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    max_continuous_sitting_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    recommended_max_continuous_sitting_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    turtle_neck_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PostureCurrentStatus(Base):
    __tablename__ = "posture_current_status"

    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), primary_key=True)
    posture_text: Mapped[str] = mapped_column(String(50), nullable=False)
    feedback_text: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class PostureHourlyStat(Base):
    __tablename__ = "posture_hourly_stat"
    __table_args__ = (
        UniqueConstraint("report_id", "hour", name="uq_posture_hourly_stat_hour"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("posture_daily_report.id"), nullable=False)
    hour: Mapped[str] = mapped_column(String(2), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    turtle_neck_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PostureLogPoint(Base):
    __tablename__ = "posture_log_point"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("posture_daily_report.id"), nullable=False)
    time: Mapped[str] = mapped_column(String(5), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PostureWeeklyReport(Base):
    __tablename__ = "posture_weekly_report"
    __table_args__ = (
        UniqueConstraint("account_id", "week_start", name="uq_posture_weekly_report_start"),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    week_start: Mapped[Date] = mapped_column(Date, nullable=False)
    week_end: Mapped[Date] = mapped_column(Date, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    average_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class PostureWeeklyTrendPoint(Base):
    __tablename__ = "posture_weekly_trend_point"

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, ForeignKey("posture_weekly_report.id"), nullable=False)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    day: Mapped[str] = mapped_column(String(5), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class ReportAnalysisItem(Base):
    __tablename__ = "report_analysis_item"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('sleep_daily', 'sleep_weekly', 'posture_daily', 'posture_weekly')",
            name="ck_report_analysis_item_type",
        ),
    )

    id: Mapped[int] = mapped_column(SqliteBigInt, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    report_id: Mapped[int] = mapped_column(SqliteBigInt, nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class Insight(Base):
    __tablename__ = "insight"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('sleep', 'posture', 'weekly-plan')",
            name="ck_insight_domain",
        ),
        CheckConstraint("period IN ('daily', 'weekly')", name="ck_insight_period"),
        Index("idx_insight_account_domain_period", "account_id", "domain", "period"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class WeeklyPlanTask(Base):
    __tablename__ = "weekly_plan_task"
    __table_args__ = (
        CheckConstraint(
            "day_of_week IN ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')",
            name="ck_weekly_plan_task_day",
        ),
        CheckConstraint(
            "category IN ('posture', 'sleep', 'diet', 'mental')",
            name="ck_weekly_plan_task_category",
        ),
        CheckConstraint("length(title) > 0", name="ck_weekly_plan_task_title"),
        CheckConstraint(
            "((start_minute IS NULL AND end_minute IS NULL) OR "
            "(start_minute IS NOT NULL AND end_minute IS NOT NULL AND "
            "start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440))",
            name="ck_weekly_plan_task_time_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    day_of_week: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str] = mapped_column(String(10), nullable=False)
    start_minute: Mapped[Optional[int]] = mapped_column(SmallInteger)
    end_minute: Mapped[Optional[int]] = mapped_column(SmallInteger)
    source_insight_id: Mapped[Optional[str]] = mapped_column(String(30), ForeignKey("insight.id"))


class Conversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        Index("idx_conversation_account_updated", "account_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False, default="새 대화")
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_message_role"),
        Index("idx_chat_message_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("conversation.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


class SuggestionChip(Base):
    __tablename__ = "suggestion_chip"
    __table_args__ = (
        CheckConstraint(
            '"group" IN (\'insight_suggestion\', \'suggestion_pool\')',
            name="ck_suggestion_chip_group",
        ),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    group: Mapped[str] = mapped_column("group", String(20), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(String(200), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class DashboardControlMode(Base):
    __tablename__ = "dashboard_control_mode"

    account_id: Mapped[str] = mapped_column(String(30), ForeignKey("account.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(30), nullable=False)
    activated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
