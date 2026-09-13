from __future__ import annotations

from typing import Any

import streamlit as st

SESSION_USER_KEY = "current_user"
SESSION_NAV_KEY = "nav_page"
SESSION_FLASH_KEY = "flash_messages"


def init_session() -> None:
    defaults = {
        SESSION_USER_KEY: None,
        SESSION_NAV_KEY: "auth",
        SESSION_FLASH_KEY: [],
        "admin_view": "dashboard",
        "student_view": "dashboard",
        "active_attempt_id": None,
        "draft_answers": {},
        "auth_tab": "Login",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def current_user() -> dict[str, Any] | None:
    return st.session_state.get(SESSION_USER_KEY)


def is_authenticated() -> bool:
    user = current_user()
    return bool(user and not user.get("blocked"))


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin" and not user.get("blocked"))


def set_user(user: dict[str, Any] | None) -> None:
    st.session_state[SESSION_USER_KEY] = user
    if user and user.get("role") == "admin":
        st.session_state["admin_view"] = "dashboard"
    elif user:
        st.session_state["student_view"] = "dashboard"


def clear_session() -> None:
    keys = list(st.session_state.keys())
    for key in keys:
        del st.session_state[key]
    init_session()


def add_flash(message: str, level: str = "info") -> None:
    messages = st.session_state.get(SESSION_FLASH_KEY, [])
    messages.append({"message": message, "level": level})
    st.session_state[SESSION_FLASH_KEY] = messages


def consume_flash() -> list[dict[str, str]]:
    messages = list(st.session_state.get(SESSION_FLASH_KEY, []))
    st.session_state[SESSION_FLASH_KEY] = []
    return messages


def show_flash() -> None:
    for item in consume_flash():
        level = item.get("level", "info")
        message = item.get("message", "")
        if level == "success":
            st.success(message)
        elif level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.info(message)
