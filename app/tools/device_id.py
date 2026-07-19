"""int <-> 16자리 소문자 hex 장치 id 변환.

DB device.id 는 INTEGER PK(1~13, JSON 배열 순서). API wire 계약은 manifest 16자리
hex(`device_list.json` id)이며, DB에는 별도 external_id 컬럼이 없다. 백엔드·에이전트는
manifest·이름·PK로 wire id ↔ 정수 id를 변환한다.

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
