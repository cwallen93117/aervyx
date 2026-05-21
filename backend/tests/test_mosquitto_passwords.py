import base64
import hashlib

import pytest

from app.services.mosquitto_passwords import (
    PBKDF2_SHA512_ITERATIONS,
    _hash_password,
    write_mosquitto_password_file,
)


def test_hash_password_uses_mosquitto_sha512_pbkdf2_format() -> None:
    salt = b"123456789012"

    hashed = _hash_password("secret", salt=salt)

    parts = hashed.split("$")
    assert parts[1] == "7"
    assert parts[2] == str(PBKDF2_SHA512_ITERATIONS)
    assert base64.b64decode(parts[3]) == salt
    assert base64.b64decode(parts[4]) == hashlib.pbkdf2_hmac(
        "sha512",
        b"secret",
        salt,
        PBKDF2_SHA512_ITERATIONS,
    )


def test_write_password_file_updates_one_user_and_preserves_others(tmp_path) -> None:
    password_file = tmp_path / "passwords"
    password_file.write_text("other:$7$101$abc$def\nfleet:old\n", encoding="utf-8")

    write_mosquitto_password_file(password_file, "fleet", "new-secret")

    lines = password_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "other:$7$101$abc$def"
    assert len(lines) == 2
    assert lines[1].startswith("fleet:$7$101$")
    assert "new-secret" not in lines[1]


@pytest.mark.parametrize("username", ["", "bad:name", "bad\nname"])
def test_write_password_file_rejects_invalid_usernames(tmp_path, username: str) -> None:
    with pytest.raises(ValueError):
        write_mosquitto_password_file(tmp_path / "passwords", username, "secret")


@pytest.mark.parametrize("password", ["", "bad\npassword"])
def test_write_password_file_rejects_invalid_passwords(tmp_path, password: str) -> None:
    with pytest.raises(ValueError):
        write_mosquitto_password_file(tmp_path / "passwords", "fleet", password)
