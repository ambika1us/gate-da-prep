from __future__ import annotations

from typing import Any

from config import get_settings
from database import get_collection
from utils.helpers import (
    generate_id,
    is_strong_password,
    is_valid_email,
    is_valid_username,
    normalize_email,
    normalize_username,
    now_utc,
    stringify_id,
    stringify_ids,
)
from utils.security import hash_password, hash_recovery_answer, verify_password


class UserService:
    def __init__(self) -> None:
        self.collection = get_collection("users")
        self.settings = get_settings()

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"_id": str(user_id)}))

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"username": normalize_username(username)}))

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"email": normalize_email(email)}))

    def find_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        identity = (identifier or "").strip().lower()
        return self.get_by_username(identity) or self.get_by_email(identity)

    def list_users(self, role: str | None = None, search: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if role:
            query["role"] = role
        if search:
            token = search.strip()
            query["$or"] = [
                {"username": {"$regex": token, "$options": "i"}},
                {"email": {"$regex": token, "$options": "i"}},
                {"full_name": {"$regex": token, "$options": "i"}},
            ]
        docs = list(self.collection.find(query).sort("created_at", -1))
        return stringify_ids(docs)

    def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: str = "student",
        recovery_question: str = "",
        recovery_answer: str = "",
        require_strong: bool = True,
    ) -> dict[str, Any]:
        username = normalize_username(username)
        email = normalize_email(email)
        full_name = (full_name or "").strip()
        if not is_valid_username(username):
            raise ValueError("Username must be 3-32 characters: letters, numbers, dot, underscore, or hyphen.")
        if not is_valid_email(email):
            raise ValueError("Enter a valid email address.")
        if not full_name:
            raise ValueError("Full name is required.")
        if role not in {"student", "admin"}:
            raise ValueError("Role must be student or admin.")
        if require_strong and not is_strong_password(password):
            raise ValueError("Password must be 8+ characters with uppercase, lowercase, digit, and symbol.")
        if len(password or "") < self.settings.min_password_length:
            raise ValueError(f"Password must be at least {self.settings.min_password_length} characters.")
        if self.get_by_username(username):
            raise ValueError("Username is already taken.")
        if self.get_by_email(email):
            raise ValueError("Email is already registered.")
        doc = {
            "_id": generate_id(),
            "username": username,
            "email": email,
            "full_name": full_name,
            "password_hash": hash_password(password),
            "role": role,
            "blocked": False,
            "recovery_question": (recovery_question or "").strip(),
            "recovery_answer_hash": hash_recovery_answer(recovery_answer) if recovery_answer else "",
            "created_at": now_utc(),
            "last_login": None,
        }
        self.collection.insert_one(doc)
        return stringify_id(doc) or doc

    def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"full_name", "email", "role", "blocked", "recovery_question"}
        payload = {k: v for k, v in updates.items() if k in allowed}
        if "email" in payload:
            payload["email"] = normalize_email(payload["email"])
            if not is_valid_email(payload["email"]):
                raise ValueError("Enter a valid email address.")
            existing = self.get_by_email(payload["email"])
            if existing and existing["_id"] != user_id:
                raise ValueError("Email is already registered.")
        if "role" in payload and payload["role"] not in {"student", "admin"}:
            raise ValueError("Role must be student or admin.")
        if "full_name" in payload:
            payload["full_name"] = str(payload["full_name"]).strip()
        if not payload:
            return self.get_by_id(user_id)
        self.collection.update_one({"_id": str(user_id)}, {"$set": payload})
        return self.get_by_id(user_id)

    def set_password(self, user_id: str, password: str, require_strong: bool = True) -> None:
        if require_strong and not is_strong_password(password):
            raise ValueError("Password must be 8+ characters with uppercase, lowercase, digit, and symbol.")
        self.collection.update_one({"_id": str(user_id)}, {"$set": {"password_hash": hash_password(password)}})

    def set_recovery(self, user_id: str, question: str, answer: str) -> None:
        self.collection.update_one(
            {"_id": str(user_id)},
            {
                "$set": {
                    "recovery_question": (question or "").strip(),
                    "recovery_answer_hash": hash_recovery_answer(answer),
                }
            },
        )

    def set_blocked(self, user_id: str, blocked: bool) -> dict[str, Any] | None:
        self.collection.update_one({"_id": str(user_id)}, {"$set": {"blocked": bool(blocked)}})
        return self.get_by_id(user_id)

    def delete_user(self, user_id: str) -> None:
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")
        if user.get("username") == self.settings.admin_username:
            raise ValueError("The bootstrap admin account cannot be deleted.")
        self.collection.delete_one({"_id": str(user_id)})

    def mark_login(self, user_id: str) -> None:
        self.collection.update_one({"_id": str(user_id)}, {"$set": {"last_login": now_utc()}})

    def authenticate(self, username_or_email: str, password: str) -> dict[str, Any]:
        user = self.find_by_identifier(username_or_email)
        if not user:
            raise ValueError("Invalid credentials.")
        if user.get("blocked"):
            raise ValueError("This account is blocked. Contact an administrator.")
        if not verify_password(password, user.get("password_hash", "")):
            raise ValueError("Invalid credentials.")
        self.mark_login(user["_id"])
        return self.get_by_id(user["_id"]) or user

    def public_profile(self, user: dict[str, Any] | None) -> dict[str, Any] | None:
        if not user:
            return None
        return {
            "_id": str(user["_id"]),
            "username": user.get("username"),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "role": user.get("role"),
            "blocked": bool(user.get("blocked", False)),
            "created_at": user.get("created_at"),
            "last_login": user.get("last_login"),
            "recovery_question": user.get("recovery_question", ""),
        }

    def count(self, role: str | None = None) -> int:
        query: dict[str, Any] = {}
        if role:
            query["role"] = role
        return self.collection.count_documents(query)
