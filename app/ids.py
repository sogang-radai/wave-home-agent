from __future__ import annotations

import os
import time

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_ulid(timestamp_ms: int, randomness: bytes) -> str:
    value = (timestamp_ms << 80) | int.from_bytes(randomness, "big")
    chars = []
    for _ in range(26):
        value, remainder = divmod(value, 32)
        chars.append(_CROCKFORD_ALPHABET[remainder])
    return "".join(reversed(chars))


def new_ulid() -> str:
    timestamp_ms = int(time.time() * 1000)
    randomness = os.urandom(10)
    return _encode_ulid(timestamp_ms, randomness)


def new_id(prefix: str) -> str:
    return f"{prefix}_{new_ulid()}"
