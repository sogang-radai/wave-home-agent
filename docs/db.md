# WaveHome DB 설계 

#### 설계 원칙

###### 저장 기준

- API에서 실제로 필요한 필드만 저장한다.
- 단, 정렬/이력 보존에 필요한 `created_at`, `updated_at`, `occurred_at` 등은 필요한 테이블에만 둔다.
- 대시보드 문장, 자동화 요약, 주간 평균 같은 값은 저장하지 않고 요청 시 계산한다.
- **캐싱 목적의 중복 컬럼은 제거한다.**
  - 예: `conversation.last_message_preview`, `conversation.message_count`는 저장하지 않는다.
  - 예: 대시보드 배너 문장 캐시 테이블은 만들지 않는다. 

###### ID 규칙

| 대상 | 예시 | 타입 |
|---|---|---|
| 계정, 알림, 채팅, 메시지, 인사이트, 일정, 제스처 이력 | `acc_*`, `noti_*`, `chat_*`, `msg_*`, `ins_*`, `task_*`, `ges_hist_*` | `VARCHAR(30)` |
| 기기 / 레이더 ID | `8d2e5a1c49f7036b` | `VARCHAR(16)` |
| 제스처 세트 / 제스처 | `daily`, `ges_1` | `VARCHAR(20)` |

###### 타입 규칙

특정 DBMS에 종속되지 않는 범용 표기를 사용한다.

| 용도 | 타입 |
|---|---|
| 문자열 | `VARCHAR`, `TEXT` |
| 정수 | `INT`, `SMALLINT`, `BIGINT` |
| 실수/금액/전력 | `DECIMAL` |
| 참/거짓 | `BOOLEAN` |
| 날짜/시간 | `DATE`, `TIME`, `DATETIME` |
| 기기별 가변 설정 | `JSON` |

###### 계정 범위

- `activeAccount` 기준 리소스는 모두 `account_id`를 FK로 갖는다.
  - 수면
  - 자세
  - 주간 계획
  - 챗봇
  - 알림
  - 설정
- 가전 제어(`home.md`)는 가구 전체 기준으로 본다.
  - `gesture`, `device`, `device_binding`, `gesture_history`에는 기본적으로 `account_id`를 두지 않는다.

---

## 1. 계정 / 세션

#### 1.1 `account` — 가구 구성원

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `acc_01J2ZQ...` |
| `name` | `VARCHAR(50)` | N |  | 구성원 이름 |

#### 1.2 `session` — 브라우저별 활성 구성원

인증 시스템 없이, 현재 브라우저가 선택한 구성원만 기억한다.  
`sid` 쿠키 1개당 1행을 저장한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `sid` | `VARCHAR(64)` | N | PK | 세션 쿠키 값 |
| `active_account_id` | `VARCHAR(30)` | N | FK → `account.id` | 현재 선택된 구성원 |
| `updated_at` | `DATETIME` | N |  | 마지막 구성원 전환 시각 |

---

## 2. 방 / 기기

#### 2.1 `room`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `room_01J2ZQ...` |
| `name` | `VARCHAR(50)` | N |  | 방 이름 |
| `description` | `VARCHAR(200)` | N |  | 빈 문자열 요청 시 서버가 `name`으로 채움 |

###### 삭제 제약

`room`에 연결된 `device`가 1개 이상 있으면 삭제할 수 없다.

```text
409 ROOM_HAS_DEVICES
```

#### 2.2 `device` — 입력/출력 기기 원본

레이더도 별도 테이블을 만들지 않고 `device`에 저장한다.  
`GET /home/radars`는 `class = 'srs_r4sn'`인 기기만 필터링해서 반환한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(16)` | N | PK | 장비 stable id |
| `room_id` | `VARCHAR(30)` | N | FK → `room.id` | 설치된 방 |
| `name` | `VARCHAR(50)` | N |  | 기기 이름 |
| `description` | `VARCHAR(200)` | Y |  | 기기 설명 |
| `enabled` | `BOOLEAN` | N |  | 기본값 `true` |
| `class` | `VARCHAR(20)` | N |  | 장비 class |
| `direction` | `VARCHAR(10)` | N |  | `input` 또는 `output` |
| `interface` | `JSON` | N |  | 장비 연결 정보 |
| `settings` | `JSON` | Y |  | 장비별 부가 설정 |

###### `device.class` 허용값

```text
srs_r4sn
wave_mic
wave_cam
ir_reciever
ir_remote
tizen_tv
tuya_ep2h
tuya_blind
hue_light
```

###### `device.direction` 허용값

```text
input
output
```

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_device_room_id(room_id)` | 방별 기기 목록 조회 |
| `idx_device_class(class)` | 레이더 목록 조회, 스마트 플러그 필터링 |

#### 2.3 `device_control` — 기기별 제어 항목

`IotDevice.controls[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `INT` | N | PK, AI | 제어 항목 ID |
| `device_id` | `VARCHAR(16)` | N | FK → `device.id` | 대상 기기 |
| `label` | `VARCHAR(30)` | N |  | 예: `전원`, `밝기 조절` |
| `hint` | `VARCHAR(100)` | N |  | 예: `손 올리기 / 손 내리기` |

###### 제약

```text
UNIQUE(device_id, label)
```

#### 2.4 `device_status` — 기기 실시간 상태

`IotDevice.state`, `IotDevice.connection`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `device_id` | `VARCHAR(16)` | N | PK, FK → `device.id` | 기기 ID |
| `state` | `VARCHAR(100)` | N |  | 예: `켜짐 · 밝기 72%` |
| `connection` | `VARCHAR(10)` | N |  | `online` 또는 `idle` |
| `updated_at` | `DATETIME` | N |  | 상태 갱신 시각 |

---

## 3. 가전 제어 / 제스처

가전 제어 리소스는 `account_id` 기준이 아니라 가구 전체 기준이다.

#### 3.1 `gesture_set`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(20)` | N | PK | `daily`, `sleep`, `focus`, `rest` |
| `name` | `VARCHAR(50)` | N |  | 예: `Daily Control` |
| `description` | `VARCHAR(200)` | N |  | 세트 설명 |

#### 3.2 `gesture`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(20)` | N | PK | `ges_1` |
| `gesture_set_id` | `VARCHAR(20)` | N | FK → `gesture_set.id` | 소속 세트 |
| `name` | `VARCHAR(50)` | N |  | 예: `손 올리기` |
| `action` | `VARCHAR(100)` | N |  | 예: `조명 켜기` |

#### 3.3 `gesture_radar_assignment` — 제스처 ↔ 레이더 N:M

제스처가 어떤 레이더에서 인식될 수 있는지 저장한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `gesture_id` | `VARCHAR(20)` | N | PK, FK → `gesture.id` | 제스처 |
| `radar_device_id` | `VARCHAR(16)` | N | PK, FK → `device.id` | 레이더 기기 |

###### 유효성 규칙

`radar_device_id`는 반드시 다음 조건을 만족해야 한다.

```sql
SELECT * FROM device
WHERE id = :radar_device_id
  AND class = 'srs_r4sn';
```

DB CHECK만으로는 다른 테이블의 `class`를 확인하기 어렵기 때문에 애플리케이션 레벨에서 검증한다.

#### 3.4 `gesture_history` — 제스처 인식 이력

과거 이력 화면은 당시 상태 그대로 보여야 한다.  
따라서 FK가 가리키는 `gesture`, `device` 이름이 나중에 바뀌더라도 이력이 변하지 않도록 snapshot 컬럼을 저장한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `ges_hist_01J2ZQ...` |
| `gesture_id` | `VARCHAR(20)` | Y | FK → `gesture.id` | 매칭된 제스처. 삭제/변경 가능성을 고려해 NULL 허용 |
| `gesture_name_snapshot` | `VARCHAR(50)` | N |  | 인식 당시 제스처 이름 |
| `device_id` | `VARCHAR(16)` | N | FK → `device.id` | 제어 대상 출력 기기 |
| `device_name_snapshot` | `VARCHAR(50)` | N |  | 인식 당시 기기 이름 |
| `radar_device_id` | `VARCHAR(16)` | N | FK → `device.id` | 인식한 레이더 |
| `action_snapshot` | `VARCHAR(100)` | N |  | 인식 당시 실행 액션 |
| `occurred_at` | `DATETIME` | N |  | 발생 시각 |
| `confidence` | `SMALLINT` | N |  | 0~100 |

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_gesture_history_occurred_at(occurred_at DESC)` | 히스토리 최신순 조회, 오늘 인식 수 집계 |

###### 파생 응답

`GET /home/gestures/today-summary`의 `recognizedCount`는 다음 조건으로 계산한다.

```sql
SELECT COUNT(*)
FROM gesture_history
WHERE occurred_at >= :today_start;
```

#### 3.5 `device_binding` — 기기 제어 ↔ 제스처 바인딩

바인딩이 없는 상태는 `NULL`이 아니라 **행 없음**으로 표현한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `control_id` | `INT` | N | PK, FK → `device_control.id` | 제어 항목 |
| `gesture_id` | `VARCHAR(20)` | N | UNIQUE, FK → `gesture.id` | 연결된 제스처 |

###### 정책

- 하나의 제어 항목은 최대 하나의 제스처에만 연결된다.
  - `control_id`가 PK이므로 보장된다.
- 하나의 제스처도 동시에 하나의 제어 항목에만 연결된다.
  - `gesture_id UNIQUE`로 보장된다.
- 이미 사용 중인 `gesture_id`로 바인딩을 시도하면 다음 오류를 반환한다.

```text
400 GESTURE_IN_USE
```

###### 바인딩 해제

바인딩 해제는 `UPDATE gesture_id = NULL`이 아니라 해당 행을 삭제한다.

```sql
DELETE FROM device_binding
WHERE control_id = :control_id;
```

---

## 4. 전력 모니터링

해커톤 구현에서는 실제 시계열 측정 원천 테이블을 따로 두지 않는다.  
대신 프론트 차트 응답에 필요한 trend 데이터를 `power_trend_point`에 직접 저장한다.

#### 4.1 `smart_plug`

`id = 'all'`은 실물 기기가 아니라 전체 콘센트 합산용 가상 행이다.  
이 경우 `device_id`는 `NULL`이다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(16)` | N | PK | `all` 또는 device id |
| `device_id` | `VARCHAR(16)` | Y | FK → `device.id` | `id = 'all'`일 때 NULL |
| `name` | `VARCHAR(50)` | N |  | 플러그 이름 |
| `power_w` | `DECIMAL(7,2)` | N |  | 현재 전력 W |
| `voltage_v` | `DECIMAL(6,2)` | N |  | 전압 V |
| `current_ma` | `DECIMAL(8,2)` | N |  | 전류 mA |
| `switch_on` | `BOOLEAN` | N |  | 스위치 상태 |
| `hourly_cost_won` | `DECIMAL(8,2)` | N |  | 시간당 예상 요금 |
| `measured_at` | `DATETIME` | N |  | 측정 시각 |

###### 참고

`summary` 문장은 저장하지 않는다.  
필요하면 현재 전력, 스위치 상태, 요금 정보를 기반으로 API 응답 시점에 생성한다.

#### 4.2 `power_trend_point`

전력 trend는 캐시가 아니라 **차트 응답을 위한 저장 데이터**로 본다.  
해커톤에서는 이 테이블을 seed/mock 데이터처럼 채워두고 API에서 그대로 조회한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | trend point ID |
| `plug_id` | `VARCHAR(16)` | N | FK → `smart_plug.id` | 대상 플러그 |
| `granularity` | `VARCHAR(10)` | N |  | `hour`, `day`, `week`, `month` |
| `seq` | `SMALLINT` | N |  | 표시 순서 |
| `label` | `VARCHAR(20)` | N |  | 예: `00:00`, `월`, `1주`, `3월` |
| `value` | `DECIMAL(10,2)` | N |  | 차트 값 |

###### 제약

```text
UNIQUE(plug_id, granularity, seq)
```

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_power_trend_plug_granularity(plug_id, granularity, seq)` | 특정 플러그의 trend 조회 |

---

## 5. 설정

#### 5.1 `sound` — 알람/알림음 카탈로그

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(50)` | N | PK | `sign-of-the-times` |
| `label` | `VARCHAR(100)` | N |  | 표시 이름 |

#### 5.2 `tts_speaker`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `INT` | N | PK | 화자 ID |
| `name` | `VARCHAR(30)` | N |  | 화자 이름 |
| `description` | `VARCHAR(100)` | N |  | 설명 |
| `character` | `VARCHAR(20)` | N |  | 캐릭터 |
| `gender` | `VARCHAR(10)` | N |  | `male`, `female` |

#### 5.3 `sleep_config` — 취침 전 자동화 설정

수면 측정/리포트가 아니라 사용자의 취침 자동화 설정이다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `account_id` | `VARCHAR(30)` | N | PK, FK → `account.id` | 구성원 |
| `bedtime` | `TIME` | N |  | 취침 목표 시각 |
| `wake_time` | `TIME` | N |  | 기상 목표 시각 |
| `wake_up_sound_id` | `VARCHAR(50)` | N | FK → `sound.id` | 알람음 |
| `ac_auto` | `BOOLEAN` | N |  | 에어컨 자동 여부 |
| `ac_temp` | `SMALLINT` | N |  | 20~28 |
| `light_auto` | `BOOLEAN` | N |  | 조명 자동 여부 |
| `dim_start_minutes` | `SMALLINT` | N |  | 10~60 |
| `final_brightness` | `SMALLINT` | N |  | 0~30 |
| `wake_light_ramp` | `BOOLEAN` | N |  | 기상 조명 ramp |
| `wake_music` | `BOOLEAN` | N |  | 기상 음악 |
| `wake_tv_or_alarm` | `BOOLEAN` | N |  | TV/알람 사용 |

#### 5.4 `general_setting`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `account_id` | `VARCHAR(30)` | N | PK, FK → `account.id` | 구성원 |
| `theme` | `VARCHAR(10)` | N |  | `light`, `dark` |
| `language` | `VARCHAR(10)` | N |  | 예: `ko`, `en` |
| `notification_sound_id` | `VARCHAR(50)` | N | FK → `sound.id` | 알림음 |
| `tts_speaker_id` | `INT` | N | FK → `tts_speaker.id` | TTS 화자 |

#### 5.5 `posture_alert_setting`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `account_id` | `VARCHAR(30)` | N | PK, FK → `account.id` | 구성원 |
| `turtle_neck` | `BOOLEAN` | N |  | 거북목 알림 |
| `waist_tilt` | `BOOLEAN` | N |  | 허리 기울임 알림 |
| `long_sitting` | `BOOLEAN` | N |  | 장시간 착석 알림 |

---

## 6. 알림

#### 6.1 `notification`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `noti_01J2ZQ...` |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 수신 구성원 |
| `type` | `VARCHAR(20)` | N |  | 알림 타입 |
| `message` | `VARCHAR(200)` | N |  | 알림 메시지 |
| `created_at` | `DATETIME` | N |  | 생성 시각 |
| `read` | `BOOLEAN` | N |  | 기본값 `false` |

###### `type` 허용값

```text
timer
sleep
posture
temperature
```

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_notification_account_created(account_id, created_at DESC)` | 알림 목록 최신순 조회 |

###### 읽음 처리

`PATCH /notifications/read-all`은 해당 구성원의 모든 알림을 읽음 처리한다.

```sql
UPDATE notification
SET read = true
WHERE account_id = :account_id;
```

#### 6.2 `push_subscription`

Firebase JS SDK의 `getToken()`이 발급한 FCM 등록 토큰을 저장한다. `notification`이 생성될 때
해당 계정의 모든 토큰으로 FCM 푸시를 함께 발송한다 (`app/push_service.py::notify_account`,
`firebase_admin.messaging` 사용).

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `psh_01J2ZQ...` |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구독 계정 |
| `token` | `VARCHAR(500)` | N | UNIQUE | FCM 등록 토큰 |
| `user_agent` | `VARCHAR(255)` | Y |  | 구독 생성 시 User-Agent |
| `created_at` | `DATETIME` | N |  | 생성 시각 |

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_push_subscription_account_id(account_id)` | 계정별 구독 목록 조회 |

###### 구독 정리

발송 시 `firebase_admin.messaging.UnregisteredError`가 발생하면(알림 권한 철회, 토큰 만료 등)
해당 행을 즉시 삭제한다.

---

## 7. 수면 트래킹

`sleep_config`는 자동화 설정이고, 아래 테이블들은 실제 측정/리포트 데이터다.

#### 7.1 `sleep_daily_report`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | 일간 리포트 ID |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `date` | `DATE` | N |  | 수면 시작일 기준 |
| `score` | `SMALLINT` | N |  | 수면 점수 |
| `sleep_window_start` | `DATETIME` | N |  | 수면 구간 시작 |
| `sleep_window_end` | `DATETIME` | N |  | 수면 구간 종료 |
| `time_in_bed_minutes` | `INT` | N |  | 침대에 있던 시간 |
| `actual_sleep_minutes` | `INT` | N |  | 실제 수면 시간 |

###### 제약

```text
UNIQUE(account_id, date)
```

###### 파생 응답

`today/summary`의 다음 값은 저장하지 않고 계산한다.

| 응답 필드 | 산출 방식 |
|---|---|
| `achievedHours` | `actual_sleep_minutes / 60` |
| `goalHours` | `sleep_config` 기반 계산 |
| `bedTime` | `sleep_window_start` 또는 `sleep_config.bedtime` |
| `wakeTime` | `sleep_window_end` 또는 `sleep_config.wake_time` |

#### 7.2 `sleep_score_factor`

`scoreFactors[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `seq` | `SMALLINT` | N |  | 표시 순서 |
| `key` | `VARCHAR(30)` | N |  | 예: `duration` |
| `label` | `VARCHAR(50)` | N |  | 표시 라벨 |
| `value` | `VARCHAR(50)` | N |  | 표시 값 |
| `tag` | `VARCHAR(20)` | N |  | 예: `주의` |
| `tone` | `VARCHAR(10)` | N |  | `attention`, `good`, `excellent` |

#### 7.3 `sleep_stage_breakdown`

`stageBreakdown[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `stage` | `VARCHAR(10)` | N |  | `awake`, `rem`, `light`, `deep` |
| `label` | `VARCHAR(20)` | N |  | 표시명 |
| `percent` | `SMALLINT` | N |  | 비율 |
| `duration_minutes` | `INT` | N |  | 지속 시간 |
| `duration_text` | `VARCHAR(20)` | N |  | 예: `1시간 14분` |
| `tone` | `VARCHAR(10)` | N |  | stage와 동일한 tone |
| `typical_percent_min` | `SMALLINT` | N |  | 일반 범위 최소 |
| `typical_percent_max` | `SMALLINT` | N |  | 일반 범위 최대 |

###### 제약

```text
UNIQUE(report_id, stage)
```

#### 7.4 `sleep_hypnogram_segment`

`hypnogram.segments[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `seq` | `SMALLINT` | N |  | 시간 순서 |
| `stage` | `VARCHAR(10)` | N |  | `awake`, `light`, `deep`, `rem` |
| `duration_minutes` | `INT` | N |  | 지속 시간 |

`hypnogram.start`, `hypnogram.end`는 `sleep_daily_report.sleep_window_start`, `sleep_daily_report.sleep_window_end`를 사용한다.

#### 7.5 `sleep_movement_level`

`hypnogram.movementLevels[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `seq` | `SMALLINT` | N |  | 샘플 순서 |
| `level` | `SMALLINT` | N |  | 0~100 |

#### 7.6 `sleep_stage_log`

`stageLog[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `time` | `VARCHAR(5)` | N |  | `HH:mm` |
| `stage` | `VARCHAR(10)` | N |  | 수면 단계 |
| `stage_label` | `VARCHAR(20)` | N |  | 표시명 |
| `breath_rate` | `SMALLINT` | N |  | 호흡수 |
| `heart_rate` | `SMALLINT` | N |  | 심박수 |
| `level` | `SMALLINT` | N |  | 단계 레벨 |

#### 7.7 `snoring_episode`

`snoringEpisodes[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_daily_report.id` | 일간 리포트 |
| `time` | `VARCHAR(5)` | N |  | 발생 시각 |
| `duration_minutes` | `INT` | N |  | 지속 시간 |

#### 7.8 `sleep_weekly_report`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | 주간 리포트 ID |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `week_start` | `DATE` | N |  | 월요일 |
| `week_end` | `DATE` | N |  | 일요일 |
| `score` | `SMALLINT` | N |  | 대표 점수 |
| `summary` | `VARCHAR(200)` | N |  | 요약 |
| `average_score` | `SMALLINT` | N |  | 평균 점수 |

###### 제약

```text
UNIQUE(account_id, week_start)
```

#### 7.9 `sleep_weekly_trend_point`

`trend[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `sleep_weekly_report.id` | 주간 리포트 |
| `date` | `DATE` | N |  | 날짜 |
| `day` | `VARCHAR(5)` | N |  | 예: `월` |
| `hours` | `DECIMAL(4,2)` | N |  | 수면 시간 |
| `score` | `SMALLINT` | N |  | 점수 |

---

## 8. 자세 트래킹

#### 8.1 `posture_daily_report`

`GET /posture/today/summary`, `/posture/today`, `/posture/reports/daily`가 공유하는 일간 원본 테이블이다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | 일간 리포트 ID |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `date` | `DATE` | N |  | 날짜 |
| `score` | `SMALLINT` | N |  | 자세 점수 |
| `summary` | `VARCHAR(200)` | Y |  | 리포트 탭 요약 |
| `correct_posture_percent` | `SMALLINT` | N |  | 정자세 비율 |
| `correct_posture_goal_percent` | `SMALLINT` | Y |  | 목표 정자세 비율 |
| `alert_accept_rate_percent` | `SMALLINT` | N |  | 알림 수락률 |
| `total_sitting_minutes` | `INT` | Y |  | 총 착석 시간 |
| `max_continuous_sitting_minutes` | `INT` | Y |  | 최대 연속 착석 |
| `recommended_max_continuous_sitting_minutes` | `INT` | Y |  | 권장 최대 연속 착석 |
| `turtle_neck_count` | `SMALLINT` | N |  | 거북목 감지 횟수 |

###### 제약

```text
UNIQUE(account_id, date)
```

###### 파생 응답

`today/summary`의 `turtleNeckLastWeekAverageCount`는 저장하지 않고 직전 7일 평균으로 계산한다.

```sql
SELECT AVG(turtle_neck_count)
FROM posture_daily_report
WHERE account_id = :account_id
  AND date >= :seven_days_ago
  AND date < :today;
```

#### 8.2 `posture_current_status`

`/posture/today`의 `current`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `account_id` | `VARCHAR(30)` | N | PK, FK → `account.id` | 구성원 |
| `posture_text` | `VARCHAR(50)` | N |  | 예: `정자세 유지 중` |
| `feedback_text` | `VARCHAR(200)` | N |  | 피드백 문구 |
| `updated_at` | `DATETIME` | N |  | 갱신 시각 |

#### 8.3 `posture_hourly_stat`

`today.hourly[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `posture_daily_report.id` | 일간 리포트 |
| `hour` | `VARCHAR(2)` | N |  | 예: `09` |
| `score` | `SMALLINT` | N |  | 시간대 점수 |
| `turtle_neck_count` | `SMALLINT` | N |  | 시간대 거북목 횟수 |

###### 제약

```text
UNIQUE(report_id, hour)
```

#### 8.4 `posture_log_point`

`reports/daily`의 `log[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `posture_daily_report.id` | 일간 리포트 |
| `time` | `VARCHAR(5)` | N |  | 예: `09:00` |
| `label` | `VARCHAR(20)` | N |  | 예: `좋음` |
| `score` | `SMALLINT` | N |  | 점수 |

#### 8.5 `posture_weekly_report`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | 주간 리포트 ID |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `week_start` | `DATE` | N |  | 월요일 |
| `week_end` | `DATE` | N |  | 일요일 |
| `score` | `SMALLINT` | N |  | 대표 점수 |
| `summary` | `VARCHAR(200)` | N |  | 요약 |
| `average_score` | `SMALLINT` | N |  | 평균 점수 |

###### 제약

```text
UNIQUE(account_id, week_start)
```

#### 8.6 `posture_weekly_trend_point`

`trend[]`에 대응한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_id` | `BIGINT` | N | FK → `posture_weekly_report.id` | 주간 리포트 |
| `date` | `DATE` | N |  | 날짜 |
| `day` | `VARCHAR(5)` | N |  | 요일 표시 |
| `score` | `SMALLINT` | N |  | 점수 |

---

## 9. 리포트 분석 / 인사이트

#### 9.1 `report_analysis_item`

수면 일간/주간, 자세 일간/주간 리포트의 `analysis[]`가 동일한 shape이므로 하나의 테이블로 통합한다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `BIGINT` | N | PK, AI | ID |
| `report_type` | `VARCHAR(20)` | N |  | 리포트 타입 |
| `report_id` | `BIGINT` | N | 논리적 FK | 각 리포트 테이블의 ID |
| `seq` | `SMALLINT` | N |  | 표시 순서 |
| `label` | `VARCHAR(50)` | N |  | 분석 라벨 |
| `value` | `VARCHAR(100)` | N |  | 표시 값 |
| `description` | `VARCHAR(200)` | N |  | 설명 |

###### `report_type` 허용값

```text
sleep_daily
sleep_weekly
posture_daily
posture_weekly
```

###### 트레이드오프

이 테이블은 폴리모픽 연관을 사용하므로 DB 레벨 FK를 직접 걸기 어렵다.  
대신 애플리케이션 레벨에서 `report_type`에 맞는 리포트 존재 여부를 검증한다.

#### 9.2 `insight`

수면/자세/주간 계획에서 공유하는 추천 액션이다.  
승인 상태는 `PATCH /insights/{insightId}`로 변경된다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `ins_01J2ZQ...` |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `domain` | `VARCHAR(20)` | N |  | `sleep`, `posture`, `weekly-plan` |
| `period` | `VARCHAR(10)` | N |  | `daily`, `weekly` |
| `label` | `VARCHAR(50)` | N |  | 그룹 라벨 |
| `title` | `VARCHAR(100)` | N |  | 제목 |
| `text` | `VARCHAR(300)` | N |  | 본문 |
| `approved` | `BOOLEAN` | N |  | 기본값 `false` |
| `created_at` | `DATETIME` | N |  | 생성 시각 |

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_insight_account_domain_period(account_id, domain, period)` | 도메인/기간별 인사이트 조회 |

###### 파생 응답

`GET /weekly-plan/recommendations`는 `insight`를 `label` 기준으로 그룹핑해 `RecommendationGroup[]`로 변환한다.

---

## 10. 주간 계획

#### 10.1 `weekly_plan_task`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `task_01J2ZQ...` |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `title` | `VARCHAR(100)` | N |  | 일정 제목. 빈 문자열 불가 |
| `done` | `BOOLEAN` | N |  | 기본값 `false` |
| `day_of_week` | `VARCHAR(3)` | N |  | 요일 |
| `category` | `VARCHAR(10)` | N |  | 카테고리 |
| `start_minute` | `SMALLINT` | Y |  | 자정 기준 시작 분 |
| `end_minute` | `SMALLINT` | Y |  | 자정 기준 종료 분 |
| `source_insight_id` | `VARCHAR(30)` | Y | FK → `insight.id` | 추천 액션에서 생성된 경우 |

###### `day_of_week` 허용값

```text
mon
tue
wed
thu
fri
sat
sun
```

###### `category` 허용값

```text
posture
sleep
diet
mental
```

###### 시간 제약

- `start_minute`, `end_minute`는 둘 다 NULL이거나 둘 다 NOT NULL이어야 한다.
- 값이 있으면 다음 조건을 만족해야 한다.

```text
0 <= start_minute < end_minute <= 1440
```

---

## 11. 챗봇

캐싱 목적의 `last_message_preview`, `message_count`는 저장하지 않는다.  
대화 목록이 필요하면 `conversation` 목록을 조회하고, 상세 진입 시 `chat_message`를 조회한다.

#### 11.1 `conversation`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `chat_01J2ZQ...` |
| `account_id` | `VARCHAR(30)` | N | FK → `account.id` | 구성원 |
| `title` | `VARCHAR(100)` | N |  | 기본값 `새 대화`, 첫 메시지 포함 생성 시 메시지 내용 |
| `created_at` | `DATETIME` | N |  | 생성 시각 |
| `updated_at` | `DATETIME` | N |  | 메시지 추가/제목 변경 시 갱신 |

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_conversation_account_updated(account_id, updated_at DESC)` | 대화 목록 최신순 조회 |

#### 11.2 `chat_message`

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(30)` | N | PK | `msg_01J2ZQ...` |
| `conversation_id` | `VARCHAR(30)` | N | FK → `conversation.id` | 대화 ID |
| `role` | `VARCHAR(10)` | N |  | `user`, `assistant` |
| `text` | `VARCHAR(2000)` | N |  | 최대 2000자 |
| `created_at` | `DATETIME` | N |  | 생성 시각 |

###### 권장 인덱스

| 인덱스 | 용도 |
|---|---|
| `idx_chat_message_conversation_created(conversation_id, created_at)` | 대화 상세 메시지 순서 조회 |

###### 메시지 추가 시 처리

`chat_message` INSERT 후 `conversation.updated_at`만 갱신한다.

```sql
UPDATE conversation
SET updated_at = :now
WHERE id = :conversation_id;
```

#### 11.3 `suggestion_chip`

추천 질문 칩이다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `id` | `VARCHAR(50)` | N | PK | `sug_insight_sleep_today` |
| `group` | `VARCHAR(20)` | N |  | `insight_suggestion`, `suggestion_pool` |
| `icon` | `VARCHAR(30)` | Y |  | `suggestion_pool`에만 존재 |
| `label` | `VARCHAR(50)` | N |  | 칩 라벨 |
| `prompt` | `VARCHAR(200)` | N |  | 실제 질의 프롬프트 |
| `seq` | `SMALLINT` | N |  | 표시 순서 |

###### 저장하지 않는 API

`POST /chat/insight-queries`는 대화 이력을 남기지 않는 1회성 질의이므로 별도 테이블을 두지 않는다.

---

## 12. 대시보드

대시보드는 대부분 다른 도메인 데이터를 조합해서 보여주는 화면이다.  
캐시 테이블은 만들지 않고, 요청 시점에 필요한 데이터를 조합한다.

#### 12.1 저장하지 않는 대시보드 응답

| API 응답 | 산출 방식 |
|---|---|
| `GET /dashboard/daily-message` | 어젯밤 수면 + 오늘 자세 + 오늘 할 일을 조합해 생성 |
| `indoorEnvironment` | 온습도/환경 센서 기기 또는 device 정보에서 파생 |
| `radar` | `device.class = 'srs_r4sn'` 필터 |
| 자세 점수 | `posture_daily_report` 재사용 |

#### 12.2 `dashboard_control_mode`

대시보드에서 현재 활성화된 제어 모드를 표시하기 위한 최소 상태값이다.  
가전 화면에 동일한 저장 리소스가 없으므로 별도 테이블로 둔다.

| 필드명 | 타입 | NULL | 키 | 설명 |
|---|---|---:|---|---|
| `account_id` | `VARCHAR(30)` | N | PK, FK → `account.id` | 구성원 |
| `label` | `VARCHAR(30)` | N |  | 예: `집중 모드` |
| `activated_at` | `DATETIME` | N |  | 활성화 시각 |

---

## 13. 저장하지 않고 파생하는 값

| 구분 | 저장하지 않는 값 | 이유 |
|---|---|---|
| 대시보드 | daily message | 다른 도메인 데이터를 조합해 생성 가능 |
| 대시보드 | indoor environment 문구 | device/센서 값에서 생성 가능 |
| 홈 | radar 목록 | `device.class = 'srs_r4sn'`로 필터 가능 |
| 홈 | 오늘 제스처 인식 수 | `gesture_history`에서 당일 집계 가능 |
| 전력 | smart plug summary 문장 | 현재 전력/스위치/요금으로 생성 가능 |
| 수면 | automation summary | `sleep_config`를 문장화하면 됨 |
| 수면 | achievedHours | `actual_sleep_minutes`로 계산 가능 |
| 자세 | turtleNeckLastWeekAverageCount | 최근 7일 `posture_daily_report` 평균 |
| 주간 계획 | recommendations group | `insight.label` 기준 그룹핑 |
| 채팅 | last message preview | 상세 메시지에서 필요 시 조회 가능 |
| 채팅 | message count | 필요 시 `COUNT(chat_message)`로 계산 가능 |
| 채팅 | insight query history | API가 stateless 질의로 정의됨 |

---

## 14. 관계 요약

```text
account 1───N session(active_account_id)
account 1───1 sleep_config
account 1───1 general_setting
account 1───1 posture_alert_setting
account 1───1 posture_current_status
account 1───1 dashboard_control_mode
account 1───N notification
account 1───N push_subscription
account 1───N insight
account 1───N weekly_plan_task
account 1───N conversation
account 1───N sleep_daily_report
account 1───N sleep_weekly_report
account 1───N posture_daily_report
account 1───N posture_weekly_report

room 1───N device
device 1───N device_control
device 1───1 device_status
device 1───1 smart_plug(nullable)
device(class=srs_r4sn) 1───N gesture_radar_assignment
device(class=srs_r4sn) 1───N gesture_history(as radar)
device 1───N gesture_history(as controlled device)

device_control 1───1 device_binding

gesture_set 1───N gesture
gesture N───M device(radar) via gesture_radar_assignment
gesture 1───1 device_binding
gesture 1───N gesture_history

smart_plug 1───N power_trend_point

sleep_daily_report 1───N sleep_score_factor
sleep_daily_report 1───N sleep_stage_breakdown
sleep_daily_report 1───N sleep_hypnogram_segment
sleep_daily_report 1───N sleep_movement_level
sleep_daily_report 1───N sleep_stage_log
sleep_daily_report 1───N snoring_episode
sleep_weekly_report 1───N sleep_weekly_trend_point

posture_daily_report 1───N posture_hourly_stat
posture_daily_report 1───N posture_log_point
posture_weekly_report 1───N posture_weekly_trend_point

sleep_daily_report | sleep_weekly_report | posture_daily_report | posture_weekly_report
  1───N report_analysis_item(logical polymorphic relation)

insight 1───N weekly_plan_task(source_insight_id nullable)

conversation 1───N chat_message
```

---

## 설계 메모

#### JSON 컬럼 사용

`device.interface`, `device.settings`는 장비 class마다 shape가 다르다.  
이를 모두 정규화하면 class별 서브테이블이 지나치게 많아지므로 JSON 컬럼으로 둔다.

#### 레이더 테이블을 만들지 않는 이유

레이더는 독립 엔티티가 아니라 `device` 중 하나다.  
따라서 별도 `radar` 테이블을 만들지 않고 다음 조건으로 조회한다.

```sql
SELECT *
FROM device
WHERE class = 'srs_r4sn';
```

#### 캐싱 제거 기준

다음처럼 성능 최적화만을 위한 중복 저장은 제거했다.

- `conversation.last_message_preview`
- `conversation.message_count`
- `dashboard_daily_messages`
- `power_device_summaries`
- 스마트 플러그 summary 문장 저장

#### 전력 trend는 유지

`power_trend_point`는 캐시가 아니라 API 차트 응답을 위한 저장 데이터로 본다.  
원천 측정값 집계보다 이 방식이 구현이 단순하고 데모 안정성이 높다.

실서비스로 확장할 경우에는 다음 구조를 추가할 수 있다.

```text
power_measurement
- device_id
- measured_at
- power_w
- voltage_v
- current_ma
- switch_on
```

그 후 `power_trend_point`를 제거하거나 materialized view 성격으로 바꿀 수 있다.