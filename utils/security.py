from __future__ import annotations

import secrets

from passlib.context import CryptContext

_pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=29000,
)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


def hash_recovery_answer(answer: str) -> str:
    return hash_password((answer or "").strip().lower())


def verify_recovery_answer(answer: str, hashed: str) -> bool:
    return verify_password((answer or "").strip().lower(), hashed)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)
