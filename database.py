from __future__ import annotations

from functools import lru_cache
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from config import get_settings

INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
    "users": [
        ([("username", 1)], {"unique": True, "name": "uniq_username"}),
        ([("email", 1)], {"unique": True, "sparse": True, "name": "uniq_email"}),
        ([("role", 1)], {"name": "idx_role"}),
        ([("blocked", 1)], {"name": "idx_blocked"}),
    ],
    "categories": [
        ([("name", 1)], {"unique": True, "name": "uniq_category_name"}),
    ],
    "questions": [
        ([("category_id", 1)], {"name": "idx_question_category"}),
        ([("type", 1), ("difficulty", 1)], {"name": "idx_question_type_diff"}),
        ([("created_at", -1)], {"name": "idx_question_created"}),
    ],
    "exams": [
        ([("title", 1)], {"name": "idx_exam_title"}),
        ([("status", 1), ("scheduled_from", 1)], {"name": "idx_exam_status_schedule"}),
        ([("is_practice", 1)], {"name": "idx_exam_practice"}),
        ([("created_at", -1)], {"name": "idx_exam_created"}),
    ],
    "attempts": [
        ([("exam_id", 1)], {"name": "idx_attempt_exam"}),
        ([("user_id", 1)], {"name": "idx_attempt_user"}),
        ([("user_id", 1), ("status", 1)], {"name": "idx_attempt_user_status"}),
        ([("submitted_at", -1)], {"name": "idx_attempt_submitted"}),
    ],
    "password_resets": [
        ([("token", 1)], {"unique": True, "name": "uniq_reset_token"}),
        ([("expires_at", 1)], {"name": "idx_reset_expiry"}),
    ],
}


def _connect_mongo():
    settings = get_settings()
    try:
        from pymongo import MongoClient

        client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=2500,
            connectTimeoutMS=2500,
        )
        client.admin.command("ping")
        return client, False
    except (ConnectionFailure, ServerSelectionTimeoutError, Exception):
        import mongomock

        return mongomock.MongoClient(), True


@lru_cache(maxsize=1)
def _runtime():
    return _connect_mongo()


def get_client():
    client, _ = _runtime()
    return client


def is_memory_fallback() -> bool:
    _, fallback = _runtime()
    return fallback


def get_db() -> Database:
    settings = get_settings()
    return get_client()[settings.mongo_db]


def get_collection(name: str) -> Collection:
    return get_db()[name]


def ensure_indexes() -> None:
    users = get_collection("users")
    users.update_many({"blocked": {"$exists": False}}, {"$set": {"blocked": False}})
    db = get_db()
    for collection_name, specs in INDEXES.items():
        collection = db[collection_name]
        for keys, options in specs:
            try:
                collection.create_index(keys, **options)
            except Exception:
                continue


def bootstrap() -> dict[str, Any]:
    ensure_indexes()
    return {
        "db_name": get_settings().mongo_db,
        "fallback": is_memory_fallback(),
        "collections": list(INDEXES.keys()),
    }
