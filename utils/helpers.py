from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def generate_id() -> str:
    return uuid.uuid4().hex


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def normalize_username(value: str) -> str:
    return (value or "").strip().lower()


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(value)))


def is_strong_password(value: str) -> bool:
    return bool(PASSWORD_RE.match(value or ""))


def is_valid_username(value: str) -> bool:
    return bool(USERNAME_RE.match(normalize_username(value)))


def percent(earned: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round((float(earned) / float(total)) * 100.0, 2)


def stringify_id(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    cloned = dict(doc)
    if "_id" in cloned:
        cloned["_id"] = str(cloned["_id"])
    return cloned


def stringify_ids(docs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [stringify_id(doc) or {} for doc in docs]


def format_dt(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value
    return value.strftime(fmt)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def letter_to_index(token: str) -> int | None:
    token = (token or "").strip().upper()
    if len(token) == 1 and "A" <= token <= "Z":
        return ord(token) - 65
    return None


def option_letter(index: int) -> str:
    return chr(65 + index) if 0 <= index < 26 else str(index)


def stringify_keys(payload: dict[Any, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        safe[str(key)] = value
    return safe


def grade_from_percentage(percentage: float) -> str:
    if percentage >= 90:
        return "A"
    if percentage >= 80:
        return "B"
    if percentage >= 70:
        return "C"
    if percentage >= 60:
        return "D"
    if percentage >= 50:
        return "E"
    return "F"


def format_duration(seconds: float | int | None) -> str:
    total = int(seconds or 0)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
