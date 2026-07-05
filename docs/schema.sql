PRAGMA foreign_keys = ON;

CREATE TABLE account (
    id VARCHAR(30) NOT NULL,
    name VARCHAR(50) NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE gesture_set (
    id VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE report_analysis_item (
    id INTEGER NOT NULL,
    report_type VARCHAR(20) NOT NULL,
    report_id INTEGER NOT NULL,
    seq SMALLINT NOT NULL,
    label VARCHAR(50) NOT NULL,
    value VARCHAR(100) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_report_analysis_item_type CHECK (report_type IN ('sleep_daily', 'sleep_weekly', 'posture_daily', 'posture_weekly'))
);

CREATE TABLE room (
    id VARCHAR(30) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(200) NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE sound (
    id VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE suggestion_chip (
    id VARCHAR(50) NOT NULL,
    "group" VARCHAR(20) NOT NULL,
    icon VARCHAR(30),
    label VARCHAR(50) NOT NULL,
    prompt VARCHAR(200) NOT NULL,
    seq SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_suggestion_chip_group CHECK ("group" IN ('insight_suggestion', 'suggestion_pool'))
);

CREATE TABLE tts_speaker (
    id INTEGER NOT NULL,
    name VARCHAR(30) NOT NULL,
    description VARCHAR(100) NOT NULL,
    character VARCHAR(20) NOT NULL,
    gender VARCHAR(10) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_tts_speaker_gender CHECK (gender IN ('male', 'female'))
);

CREATE TABLE conversation (
    id VARCHAR(30) NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    title VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE INDEX idx_conversation_account_updated ON conversation (account_id, updated_at);

CREATE TABLE dashboard_control_mode (
    account_id VARCHAR(30) NOT NULL,
    label VARCHAR(30) NOT NULL,
    activated_at DATETIME NOT NULL,
    PRIMARY KEY (account_id),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE device (
    id VARCHAR(16) NOT NULL,
    room_id VARCHAR(30) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(200),
    enabled BOOLEAN NOT NULL,
    class VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    interface JSON NOT NULL,
    settings JSON,
    PRIMARY KEY (id),
    CONSTRAINT ck_device_class CHECK (class IN ('srs_r4sn', 'wave_mic', 'wave_cam', 'ir_reciever', 'ir_remote', 'tizen_tv', 'tuya_ep2h', 'tuya_blind', 'hue_light')),
    CONSTRAINT ck_device_direction CHECK (direction IN ('input', 'output')),
    FOREIGN KEY(room_id) REFERENCES room (id)
);

CREATE INDEX idx_device_room_id ON device (room_id);
CREATE INDEX idx_device_class ON device (class);

CREATE TABLE general_setting (
    account_id VARCHAR(30) NOT NULL,
    theme VARCHAR(10) NOT NULL,
    language VARCHAR(10) NOT NULL,
    notification_sound_id VARCHAR(50) NOT NULL,
    tts_speaker_id INTEGER NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT ck_general_setting_theme CHECK (theme IN ('light', 'dark')),
    FOREIGN KEY(account_id) REFERENCES account (id),
    FOREIGN KEY(notification_sound_id) REFERENCES sound (id),
    FOREIGN KEY(tts_speaker_id) REFERENCES tts_speaker (id)
);

CREATE TABLE gesture (
    id VARCHAR(20) NOT NULL,
    gesture_set_id VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(gesture_set_id) REFERENCES gesture_set (id)
);

CREATE TABLE insight (
    id VARCHAR(30) NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    domain VARCHAR(20) NOT NULL,
    period VARCHAR(10) NOT NULL,
    label VARCHAR(50) NOT NULL,
    title VARCHAR(100) NOT NULL,
    text VARCHAR(300) NOT NULL,
    approved BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_insight_domain CHECK (domain IN ('sleep', 'posture', 'weekly-plan')),
    CONSTRAINT ck_insight_period CHECK (period IN ('daily', 'weekly')),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE INDEX idx_insight_account_domain_period ON insight (account_id, domain, period);

CREATE TABLE notification (
    id VARCHAR(30) NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    type VARCHAR(20) NOT NULL,
    message VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL,
    read BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_notification_type CHECK (type IN ('timer', 'sleep', 'posture', 'temperature')),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE INDEX idx_notification_account_created ON notification (account_id, created_at);

CREATE TABLE push_subscription (
    id VARCHAR(30) NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    token VARCHAR(500) NOT NULL,
    user_agent VARCHAR(255),
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_push_subscription_token UNIQUE (token),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE INDEX idx_push_subscription_account_id ON push_subscription (account_id);

CREATE TABLE posture_alert_setting (
    account_id VARCHAR(30) NOT NULL,
    turtle_neck BOOLEAN NOT NULL,
    waist_tilt BOOLEAN NOT NULL,
    long_sitting BOOLEAN NOT NULL,
    PRIMARY KEY (account_id),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE posture_current_status (
    account_id VARCHAR(30) NOT NULL,
    posture_text VARCHAR(50) NOT NULL,
    feedback_text VARCHAR(200) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (account_id),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE posture_daily_report (
    id INTEGER NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    date DATE NOT NULL,
    score SMALLINT NOT NULL,
    summary VARCHAR(200),
    correct_posture_percent SMALLINT NOT NULL,
    correct_posture_goal_percent SMALLINT,
    alert_accept_rate_percent SMALLINT NOT NULL,
    total_sitting_minutes INTEGER,
    max_continuous_sitting_minutes INTEGER,
    recommended_max_continuous_sitting_minutes INTEGER,
    turtle_neck_count SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_posture_daily_report_date UNIQUE (account_id, date),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE posture_weekly_report (
    id INTEGER NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    score SMALLINT NOT NULL,
    summary VARCHAR(200) NOT NULL,
    average_score SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_posture_weekly_report_start UNIQUE (account_id, week_start),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE session (
    sid VARCHAR(64) NOT NULL,
    active_account_id VARCHAR(30) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (sid),
    FOREIGN KEY(active_account_id) REFERENCES account (id)
);

CREATE TABLE sleep_config (
    account_id VARCHAR(30) NOT NULL,
    bedtime TIME NOT NULL,
    wake_time TIME NOT NULL,
    wake_up_sound_id VARCHAR(50) NOT NULL,
    ac_auto BOOLEAN NOT NULL,
    ac_temp SMALLINT NOT NULL,
    light_auto BOOLEAN NOT NULL,
    dim_start_minutes SMALLINT NOT NULL,
    final_brightness SMALLINT NOT NULL,
    wake_light_ramp BOOLEAN NOT NULL,
    wake_music BOOLEAN NOT NULL,
    wake_tv_or_alarm BOOLEAN NOT NULL,
    PRIMARY KEY (account_id),
    CONSTRAINT ck_sleep_config_ac_temp CHECK (ac_temp BETWEEN 20 AND 28),
    CONSTRAINT ck_sleep_config_dim_start_minutes CHECK (dim_start_minutes BETWEEN 10 AND 60),
    CONSTRAINT ck_sleep_config_final_brightness CHECK (final_brightness BETWEEN 0 AND 30),
    FOREIGN KEY(account_id) REFERENCES account (id),
    FOREIGN KEY(wake_up_sound_id) REFERENCES sound (id)
);

CREATE TABLE sleep_daily_report (
    id INTEGER NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    date DATE NOT NULL,
    score SMALLINT NOT NULL,
    sleep_window_start DATETIME NOT NULL,
    sleep_window_end DATETIME NOT NULL,
    time_in_bed_minutes INTEGER NOT NULL,
    actual_sleep_minutes INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_sleep_daily_report_date UNIQUE (account_id, date),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE sleep_weekly_report (
    id INTEGER NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    score SMALLINT NOT NULL,
    summary VARCHAR(200) NOT NULL,
    average_score SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_sleep_weekly_report_start UNIQUE (account_id, week_start),
    FOREIGN KEY(account_id) REFERENCES account (id)
);

CREATE TABLE chat_message (
    id VARCHAR(30) NOT NULL,
    conversation_id VARCHAR(30) NOT NULL,
    role VARCHAR(10) NOT NULL,
    text VARCHAR(2000) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_chat_message_role CHECK (role IN ('user', 'assistant')),
    FOREIGN KEY(conversation_id) REFERENCES conversation (id)
);

CREATE INDEX idx_chat_message_conversation_created ON chat_message (conversation_id, created_at);

CREATE TABLE device_control (
    id INTEGER NOT NULL,
    device_id VARCHAR(16) NOT NULL,
    label VARCHAR(30) NOT NULL,
    hint VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_device_control_label UNIQUE (device_id, label),
    FOREIGN KEY(device_id) REFERENCES device (id)
);

CREATE TABLE device_status (
    device_id VARCHAR(16) NOT NULL,
    state VARCHAR(100) NOT NULL,
    connection VARCHAR(10) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (device_id),
    CONSTRAINT ck_device_status_connection CHECK (connection IN ('online', 'idle')),
    FOREIGN KEY(device_id) REFERENCES device (id)
);

CREATE TABLE gesture_history (
    id VARCHAR(30) NOT NULL,
    gesture_id VARCHAR(20),
    gesture_name_snapshot VARCHAR(50) NOT NULL,
    device_id VARCHAR(16) NOT NULL,
    device_name_snapshot VARCHAR(50) NOT NULL,
    radar_device_id VARCHAR(16) NOT NULL,
    action_snapshot VARCHAR(100) NOT NULL,
    occurred_at DATETIME NOT NULL,
    confidence SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_gesture_history_confidence CHECK (confidence BETWEEN 0 AND 100),
    FOREIGN KEY(gesture_id) REFERENCES gesture (id),
    FOREIGN KEY(device_id) REFERENCES device (id),
    FOREIGN KEY(radar_device_id) REFERENCES device (id)
);

CREATE INDEX idx_gesture_history_occurred_at ON gesture_history (occurred_at);

CREATE TABLE gesture_radar_assignment (
    gesture_id VARCHAR(20) NOT NULL,
    radar_device_id VARCHAR(16) NOT NULL,
    PRIMARY KEY (gesture_id, radar_device_id),
    FOREIGN KEY(gesture_id) REFERENCES gesture (id),
    FOREIGN KEY(radar_device_id) REFERENCES device (id)
);

CREATE TABLE posture_hourly_stat (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    hour VARCHAR(2) NOT NULL,
    score SMALLINT NOT NULL,
    turtle_neck_count SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_posture_hourly_stat_hour UNIQUE (report_id, hour),
    FOREIGN KEY(report_id) REFERENCES posture_daily_report (id)
);

CREATE TABLE posture_log_point (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    time VARCHAR(5) NOT NULL,
    label VARCHAR(20) NOT NULL,
    score SMALLINT NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES posture_daily_report (id)
);

CREATE TABLE posture_weekly_trend_point (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    date DATE NOT NULL,
    day VARCHAR(5) NOT NULL,
    score SMALLINT NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES posture_weekly_report (id)
);

CREATE TABLE sleep_hypnogram_segment (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    seq SMALLINT NOT NULL,
    stage VARCHAR(10) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_sleep_hypnogram_stage CHECK (stage IN ('awake', 'light', 'deep', 'rem')),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE sleep_movement_level (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    seq SMALLINT NOT NULL,
    level SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_sleep_movement_level CHECK (level BETWEEN 0 AND 100),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE sleep_score_factor (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    seq SMALLINT NOT NULL,
    "key" VARCHAR(30) NOT NULL,
    label VARCHAR(50) NOT NULL,
    value VARCHAR(50) NOT NULL,
    tag VARCHAR(20) NOT NULL,
    tone VARCHAR(10) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE sleep_stage_breakdown (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    stage VARCHAR(10) NOT NULL,
    label VARCHAR(20) NOT NULL,
    percent SMALLINT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    duration_text VARCHAR(20) NOT NULL,
    tone VARCHAR(10) NOT NULL,
    typical_percent_min SMALLINT NOT NULL,
    typical_percent_max SMALLINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_sleep_stage_breakdown_stage CHECK (stage IN ('awake', 'rem', 'light', 'deep')),
    CONSTRAINT uq_sleep_stage_breakdown_stage UNIQUE (report_id, stage),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE sleep_stage_log (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    time VARCHAR(5) NOT NULL,
    stage VARCHAR(10) NOT NULL,
    stage_label VARCHAR(20) NOT NULL,
    breath_rate SMALLINT NOT NULL,
    heart_rate SMALLINT NOT NULL,
    level SMALLINT NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE sleep_weekly_trend_point (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    date DATE NOT NULL,
    day VARCHAR(5) NOT NULL,
    hours NUMERIC(4, 2) NOT NULL,
    score SMALLINT NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES sleep_weekly_report (id)
);

CREATE TABLE smart_plug (
    id VARCHAR(16) NOT NULL,
    device_id VARCHAR(16),
    name VARCHAR(50) NOT NULL,
    power_w NUMERIC(7, 2) NOT NULL,
    voltage_v NUMERIC(6, 2) NOT NULL,
    current_ma NUMERIC(8, 2) NOT NULL,
    switch_on BOOLEAN NOT NULL,
    hourly_cost_won NUMERIC(8, 2) NOT NULL,
    measured_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(device_id) REFERENCES device (id)
);

CREATE TABLE snoring_episode (
    id INTEGER NOT NULL,
    report_id INTEGER NOT NULL,
    time VARCHAR(5) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(report_id) REFERENCES sleep_daily_report (id)
);

CREATE TABLE weekly_plan_task (
    id VARCHAR(30) NOT NULL,
    account_id VARCHAR(30) NOT NULL,
    title VARCHAR(100) NOT NULL,
    done BOOLEAN NOT NULL,
    day_of_week VARCHAR(3) NOT NULL,
    category VARCHAR(10) NOT NULL,
    start_minute SMALLINT,
    end_minute SMALLINT,
    source_insight_id VARCHAR(30),
    PRIMARY KEY (id),
    CONSTRAINT ck_weekly_plan_task_day CHECK (day_of_week IN ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')),
    CONSTRAINT ck_weekly_plan_task_category CHECK (category IN ('posture', 'sleep', 'diet', 'mental')),
    CONSTRAINT ck_weekly_plan_task_title CHECK (length(title) > 0),
    CONSTRAINT ck_weekly_plan_task_time_range CHECK (((start_minute IS NULL AND end_minute IS NULL) OR (start_minute IS NOT NULL AND end_minute IS NOT NULL AND start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440))),
    FOREIGN KEY(account_id) REFERENCES account (id),
    FOREIGN KEY(source_insight_id) REFERENCES insight (id)
);

CREATE TABLE device_binding (
    control_id INTEGER NOT NULL,
    gesture_id VARCHAR(20) NOT NULL,
    PRIMARY KEY (control_id),
    FOREIGN KEY(control_id) REFERENCES device_control (id),
    UNIQUE (gesture_id),
    FOREIGN KEY(gesture_id) REFERENCES gesture (id)
);

CREATE TABLE power_trend_point (
    id INTEGER NOT NULL,
    plug_id VARCHAR(16) NOT NULL,
    granularity VARCHAR(10) NOT NULL,
    seq SMALLINT NOT NULL,
    label VARCHAR(20) NOT NULL,
    value NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_power_trend_granularity CHECK (granularity IN ('hour', 'day', 'week', 'month')),
    CONSTRAINT uq_power_trend_point UNIQUE (plug_id, granularity, seq),
    FOREIGN KEY(plug_id) REFERENCES smart_plug (id)
);

CREATE INDEX idx_power_trend_plug_granularity ON power_trend_point (plug_id, granularity, seq);
