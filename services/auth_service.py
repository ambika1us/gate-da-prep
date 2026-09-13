from __future__ import annotations

from datetime import timedelta
from typing import Any

from config import get_settings
from database import get_collection
from services.user_service import UserService
from utils.helpers import generate_id, now_utc, stringify_id
from utils.security import generate_reset_token, verify_password, verify_recovery_answer
from utils.session import clear_session, set_user


class AuthService:
    def __init__(self) -> None:
        self.users = UserService()
        self.settings = get_settings()
        self.resets = get_collection("password_resets")

    def ensure_bootstrap_admin(self) -> dict[str, Any] | None:
        existing = self.users.get_by_username(self.settings.admin_username)
        if existing:
            return existing
        return self.users.create_user(
            username=self.settings.admin_username,
            email=self.settings.admin_email,
            full_name="System Administrator",
            password=self.settings.admin_password,
            role="admin",
            recovery_question="What is the default admin username?",
            recovery_answer=self.settings.admin_username,
            require_strong=False,
        )

    def register_student(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        confirm_password: str,
        recovery_question: str,
        recovery_answer: str,
    ) -> dict[str, Any]:
        if password != confirm_password:
            raise ValueError("Passwords do not match.")
        if not (recovery_question or "").strip() or not (recovery_answer or "").strip():
            raise ValueError("Recovery question and answer are required.")
        user = self.users.create_user(
            username=username,
            email=email,
            full_name=full_name,
            password=password,
            role="student",
            recovery_question=recovery_question,
            recovery_answer=recovery_answer,
        )
        return self.users.public_profile(user) or user

    def login(self, username_or_email: str, password: str) -> dict[str, Any]:
        user = self.users.authenticate(username_or_email, password)
        profile = self.users.public_profile(user) or user
        set_user(profile)
        return profile

    def logout(self) -> None:
        clear_session()

    def get_recovery_question(self, username_or_email: str) -> str:
        user = self.users.find_by_identifier(username_or_email)
        if not user:
            raise ValueError("Account not found.")
        question = user.get("recovery_question") or ""
        if not question:
            raise ValueError("Recovery is not configured for this account.")
        return question

    def recover_password(
        self,
        username_or_email: str,
        recovery_answer: str,
        new_password: str,
        confirm_password: str,
    ) -> None:
        user = self.users.find_by_identifier(username_or_email)
        if not user:
            raise ValueError("Account not found.")
        if user.get("blocked"):
            raise ValueError("This account is blocked.")
        if not user.get("recovery_answer_hash"):
            raise ValueError("Recovery is not configured for this account.")
        if not verify_recovery_answer(recovery_answer, user["recovery_answer_hash"]):
            raise ValueError("Recovery answer is incorrect.")
        if new_password != confirm_password:
            raise ValueError("Passwords do not match.")
        self.users.set_password(user["_id"], new_password)

    def create_reset_token(self, username_or_email: str) -> str:
        user = self.users.find_by_identifier(username_or_email)
        if not user:
            raise ValueError("Account not found.")
        token = generate_reset_token()
        self.resets.insert_one(
            {
                "_id": generate_id(),
                "token": token,
                "user_id": user["_id"],
                "expires_at": now_utc() + timedelta(hours=1),
                "created_at": now_utc(),
            }
        )
        return token

    def reset_with_token(self, token: str, new_password: str, confirm_password: str) -> None:
        record = stringify_id(self.resets.find_one({"token": (token or "").strip()}))
        if not record:
            raise ValueError("Reset token is invalid.")
        if record.get("expires_at") and now_utc() > record["expires_at"]:
            self.resets.delete_one({"_id": record["_id"]})
            raise ValueError("Reset token has expired.")
        if new_password != confirm_password:
            raise ValueError("Passwords do not match.")
        self.users.set_password(record["user_id"], new_password)
        self.resets.delete_one({"_id": record["_id"]})

    def change_password(self, user_id: str, current_password: str, new_password: str, confirm_password: str) -> None:
        user = self.users.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")
        if not verify_password(current_password, user.get("password_hash", "")):
            raise ValueError("Current password is incorrect.")
        if new_password != confirm_password:
            raise ValueError("Passwords do not match.")
        self.users.set_password(user_id, new_password)
