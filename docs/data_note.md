# Data Notes

현재 Agent Server는 SQLite를 직접 열지 않는다. 이 문서는 실제 DDL의 원본이 아니라, 에이전트가 백엔드 API를 통해 기대하는 논리적 데이터 영역을 정리한 안내 문서다.

## 에이전트가 기대하는 데이터 영역

| 영역 | 테이블/컬렉션 |
| --- | --- |
| 사용자/방/권한 | `user`, `room`, `room_user_map` |
| 기기/제어 | `device`, `device_user_map`, `device_room_map`, `device_control` |
| 일정 | `routine_task`, `event` |
| 수면 | `sleep_session`, `sleep_stat`, `sleep_report`, `vec_sleep_stat`, `vec_sleep_report` |
| 전력 | `power_energy`, `power_report`, `vec_power_report` |
| 기타 조회 | `gesture_set`, `gesture_log`, `notification`, `chat_history`, `insight` |

## 논리 스키마 메모

```text
user(id, ...)
room(id, ...)
room_user_map(roomId, userId)
chat_history(id, userId, createdAt, ...)

Devices
device(id, class, archived, ...)
device_user_map(deviceId, userId)
device_room_map(deviceId, roomId)
device_control(id, deviceId, label, type, ...)

Routine and one-off schedule items
routine_task(id, userId, category, dayOfWeek, startMinute, endMinute, done, createdBy, ...)
event(id, userId, date, category, startMinute, endMinute, done, ...)

Sleep raw/session/stat/report data
sleep_session(id, userId, roomId, radarId, nightDate, onset, finalWake, timeInBedS, asleepTotalS, efficiency, ...)
sleep_stat(id, userId, roomId, sessionId, granularity, timeStart, timeEnd, coverage, stageLabel, hrMean, ...)
sleep_report(id, userId, period, periodStart, reportText, model, ...)
vec_sleep_stat(statId, embedding)
vec_sleep_report(reportId, embedding)

Power data
power_energy(id, deviceId, granularity, timeStart, energyWh, coverage, sampleCount, ...)
power_report(id, energyId, deviceId, period, periodStart, reportText, model, ...)
vec_power_report(reportId, embedding)

Other queryable areas currently allowed by query_db
gesture_set(id, archived, ...)
gesture_log(id, gestureSetId, radarId, deviceId, classId, timestamp, ...)
notification(id, userId, type, read, createdAt, ...)
insight(id, userId, domain, period, approved, createdAt, ...)
```

## 아직 필요한 데이터

- 자세 리포트를 위한 `posture_*` raw/stat/report 테이블
- 자세 RAG collection
- 카메라/관측 이벤트 테이블
- 1회성 일정 `event`의 백엔드 API 반영 여부 확인
