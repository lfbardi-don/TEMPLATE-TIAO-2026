"""Identity values and password hashing for local preventive-inspection accounts."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import datetime
from hashlib import scrypt
from hmac import compare_digest
from os import urandom
import re
from typing import Literal, Mapping


Role = Literal["ADMIN", "INSURER", "INSPECTOR", "FLEET_MANAGER"]


@dataclass(frozen=True)
class Principal:
    id: str
    worker_id: str
    role: Role
    fleet_id: str | None


@dataclass(frozen=True)
class AdminAccount:
    id: str
    worker_id: str
    role: Role
    fleet_id: str | None
    active: bool
    created_at_utc: datetime


@dataclass(frozen=True)
class AdminUserEvent:
    id: str
    target_user_id: str
    target_worker_id: str
    actor_user_id: str
    actor_worker_id: str
    action: Literal["CREATE", "UPDATE", "RESET_PASSWORD"]
    occurred_at_utc: datetime
    details: Mapping[str, object]


_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 32


def validate_worker_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,20}", value) is None:
        raise ValueError("worker_id must contain 1 to 20 ASCII digits")
    return value


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must have at least 12 characters")
    salt = urandom(16)
    derived = scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LENGTH,
    )
    return f"scrypt:{_SCRYPT_N}:{_SCRYPT_R}:{_SCRYPT_P}:{_encode(salt)}:{_encode(derived)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, encoded_salt, encoded_key = stored.split(":")
        n, r, p = int(n_text), int(r_text), int(p_text)
        if (algorithm, n, r, p) != ("scrypt", _SCRYPT_N, _SCRYPT_R, _SCRYPT_P):
            return False
        salt, expected = _decode(encoded_salt), _decode(encoded_key)
        if len(salt) != 16 or len(expected) != _KEY_LENGTH:
            return False
        derived = scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (Base64Error, UnicodeError, ValueError):
        return False
    return compare_digest(derived, expected)


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))
