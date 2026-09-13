from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import bootstrap, ensure_indexes, get_collection
from services.question_service import normalize_difficulty, normalize_type
from utils.helpers import now_utc


def migrate_users() -> int:
    updated = 0
    collection = get_collection("users")
    for user in collection.find({}):
        patch = {}
        if "blocked" not in user:
            patch["blocked"] = False
        if "role" not in user:
            patch["role"] = "student"
        if "created_at" not in user:
            patch["created_at"] = now_utc()
        if "last_login" not in user:
            patch["last_login"] = None
        if "recovery_question" not in user:
            patch["recovery_question"] = ""
        if "recovery_answer_hash" not in user:
            patch["recovery_answer_hash"] = ""
        if patch:
            collection.update_one({"_id": user["_id"]}, {"$set": patch})
            updated += 1
    return updated


def migrate_questions() -> int:
    updated = 0
    collection = get_collection("questions")
    for question in collection.find({}):
        patch = {}
        if "text" not in question and question.get("prompt"):
            patch["text"] = question.get("prompt")
        if question.get("type") in {"single", "multiple", "true_false"} or "type" not in question:
            patch["type"] = normalize_type(question.get("type") or "mcq")
        if question.get("difficulty") in {"easy", "medium", "hard"} or "difficulty" not in question:
            patch["difficulty"] = normalize_difficulty(question.get("difficulty") or "Medium")
        if "marks" not in question:
            patch["marks"] = float(question.get("points") or 1)
        if patch:
            collection.update_one({"_id": question["_id"]}, {"$set": patch})
            updated += 1
    return updated


def migrate_exams() -> int:
    updated = 0
    collection = get_collection("exams")
    for exam in collection.find({}):
        patch = {}
        if "status" not in exam:
            patch["status"] = "published" if exam.get("published") else "draft"
        if "selection_mode" not in exam:
            patch["selection_mode"] = "manual"
        if "is_practice" not in exam:
            patch["is_practice"] = False
        if "allow_negative_marking" not in exam:
            patch["allow_negative_marking"] = False
        if "negative_fraction" not in exam:
            patch["negative_fraction"] = 0.33
        if "randomize_options" not in exam:
            patch["randomize_options"] = bool(exam.get("shuffle_options", True))
        if "scheduled_from" not in exam and exam.get("available_from"):
            patch["scheduled_from"] = exam.get("available_from")
        if "scheduled_to" not in exam and exam.get("available_until"):
            patch["scheduled_to"] = exam.get("available_until")
        if patch:
            collection.update_one({"_id": exam["_id"]}, {"$set": patch})
            updated += 1
    return updated


def main() -> None:
    bootstrap()
    ensure_indexes()
    print(f"Migrated users: {migrate_users()}")
    print(f"Migrated questions: {migrate_questions()}")
    print(f"Migrated exams: {migrate_exams()}")


if __name__ == "__main__":
    main()
