from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

HASH_PATTERN = re.compile(r"^pbkdf2-sha256\$(\d+)\$([a-fA-F0-9]{16,128})\$([a-fA-F0-9]{64})$")


def make_password_hash(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("访问密钥须为 12–1024 个字符")
    salt = secrets.token_bytes(24)
    count = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, count)
    return f"pbkdf2-sha256${count}${salt.hex()}${digest.hex()}"


def read_password_hash(path: Path) -> str:
    try:
        value = path.read_text().strip()
    except OSError:
        raise ValueError("访问密钥尚未配置；请运行 python -m server configure") from None
    match = HASH_PATTERN.fullmatch(value)
    if not match or not 10_000 <= int(match[1]) <= 2_000_000 or len(match[2]) % 2:
        raise ValueError("访问密钥摘要格式不正确")
    return value


def verify_password(password: str, encoded: str) -> bool:
    match = HASH_PATTERN.fullmatch(encoded)
    if not match:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(match[2]), int(match[1]))
    return hmac.compare_digest(candidate, bytes.fromhex(match[3]))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(32)
