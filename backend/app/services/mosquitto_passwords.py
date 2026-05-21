from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

PBKDF2_SHA512_ALGORITHM_ID = "7"
PBKDF2_SHA512_ITERATIONS = 101
SALT_BYTES = 12


def _validate_username(username: str) -> str:
    value = username.strip()
    if not value:
        raise ValueError("MQTT username is required.")
    if ":" in value or "\n" in value or "\r" in value:
        raise ValueError("MQTT username cannot contain colons or line breaks.")
    return value


def _validate_password(password: str) -> str:
    if not password:
        raise ValueError("MQTT password is required.")
    if "\n" in password or "\r" in password:
        raise ValueError("MQTT password cannot contain line breaks.")
    return password


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt_bytes = salt if salt is not None else os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt_bytes,
        PBKDF2_SHA512_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt_bytes).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"${PBKDF2_SHA512_ALGORITHM_ID}${PBKDF2_SHA512_ITERATIONS}${salt_b64}${digest_b64}"


def write_mosquitto_password_file(path: str | Path, username: str, password: str) -> None:
    """Create/update a Mosquitto sha512-pbkdf2 password file.

    Mosquitto's password file is line-based. Preserve any unrelated users in
    case the operator later adds diagnostics or bridge credentials by hand.
    """
    validated_username = _validate_username(username)
    validated_password = _validate_password(password)
    password_path = Path(path)
    password_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if password_path.exists():
        existing_lines = [
            line
            for line in password_path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith(f"{validated_username}:")
        ]

    existing_lines.append(f"{validated_username}:{_hash_password(validated_password)}")
    tmp_path = password_path.with_name(f".{password_path.name}.tmp")
    tmp_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
    tmp_path.replace(password_path)
