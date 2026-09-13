from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st

        secrets = getattr(st, "secrets", None)
        if secrets is not None:
            if key in secrets:
                return str(secrets[key])
            mongo = secrets.get("mongo", {}) if hasattr(secrets, "get") else {}
            mapping = {
                "MONGO_URI": "uri",
                "MONGO_DB": "db",
            }
            if key in mapping and mapping[key] in mongo:
                return str(mongo[mapping[key]])
    except Exception:
        pass
    value = os.getenv(key)
    if value:
        return value
    aliases = {
        "MONGO_DB": "MONGO_DB_NAME",
        "SESSION_SECRET": "APP_SECRET",
        "ADMIN_USERNAME": "BOOTSTRAP_ADMIN_USERNAME",
        "ADMIN_PASSWORD": "BOOTSTRAP_ADMIN_PASSWORD",
        "ADMIN_EMAIL": "BOOTSTRAP_ADMIN_EMAIL",
    }
    alias = aliases.get(key)
    if alias:
        aliased = os.getenv(alias)
        if aliased:
            return aliased
    return default


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_db: str
    app_name: str
    session_secret: str
    admin_username: str
    admin_password: str
    admin_email: str
    min_password_length: int
    seed_demo: bool


class Config:
    def __init__(self) -> None:
        settings = get_settings()
        self.mongo_uri = settings.mongo_uri
        self.mongo_db = settings.mongo_db
        self.app_name = settings.app_name
        self.session_secret = settings.session_secret
        self.admin_username = settings.admin_username
        self.admin_password = settings.admin_password
        self.admin_email = settings.admin_email


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    seed_raw = (_secret("SEED_DEMO", "true") or "true").strip().lower()
    return Settings(
        mongo_uri=_secret("MONGO_URI", "mongodb://127.0.0.1:27017/examadmin"),
        mongo_db=_secret("MONGO_DB", "examadmin"),
        app_name=_secret("APP_NAME", "GATE DA Prep"),
        session_secret=_secret("SESSION_SECRET", "change-me-in-production"),
        admin_username=_secret("ADMIN_USERNAME", "admin").lower(),
        admin_password=_secret("ADMIN_PASSWORD", "Admin@123"),
        admin_email=_secret("ADMIN_EMAIL", "admin@example.com").lower(),
        min_password_length=int(_secret("MIN_PASSWORD_LENGTH", "8")),
        seed_demo=seed_raw in {"1", "true", "yes", "on"},
    )
