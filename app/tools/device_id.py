"""int <-> 16자리 소문자 hex 장치 id 변환.

DB device.id 는 INTEGER PK. device-tool-api.md/alarms-api.md 의 wire 계약은 16자리
hex 문자열을 쓰지만 DB에 별도 external_id 컬럼은 없다(agent-be/db-schema.md:749 —
"API 응답의 deviceId·radarDeviceId 는 백엔드가 device 테이블의 16자리 hex 외부 id로
변환한다", 즉 백엔드가 정수 id로부터 즉석에서 zero-pad hex를 계산해 내려준다).

에이전트 내부(툴 시그니처, 도메인 로직)는 항상 int 를 쓰고, 변환은
app/tools/*_internal.py 의 httpx 호출 경계에서만 한다.
"""


def device_id_to_hex(device_id: int) -> str:
    return format(device_id, "016x")


def hex_to_device_id(hex_id: str) -> int:
    return int(hex_id, 16)


def device_id_to_hex_or_none(device_id: int | None) -> str | None:
    return None if device_id is None else device_id_to_hex(device_id)


def hex_to_device_id_or_none(hex_id: str | None) -> int | None:
    return None if hex_id is None else hex_to_device_id(hex_id)
