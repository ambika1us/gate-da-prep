from __future__ import annotations

import streamlit as st

from config import get_settings
from services.auth_service import AuthService
from utils.session import add_flash


def render_auth() -> None:
    settings = get_settings()
    st.markdown(f"## {settings.app_name}")
    st.caption("Sign in to continue to the examination portal.")
    tabs = st.tabs(["Login", "Register", "Reset password"])
    with tabs[0]:
        _login()
    with tabs[1]:
        _register()
    with tabs[2]:
        _reset()
    with st.expander("Demo accounts"):
        st.write(f"Admin: `{settings.admin_username}` / `{settings.admin_password}`")
        st.write("Student: `student` / `Student@123`")


def _login() -> None:
    auth = AuthService()
    with st.form("login_form"):
        identity = st.text_input("Username or email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
    if submitted:
        try:
            profile = auth.login(identity, password)
            add_flash(f"Welcome back, {profile.get('full_name') or profile.get('username')}.", "success")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _register() -> None:
    auth = AuthService()
    with st.form("register_form"):
        full_name = st.text_input("Full name")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        recovery_question = st.text_input("Recovery question")
        recovery_answer = st.text_input("Recovery answer")
        submitted = st.form_submit_button("Create student account", use_container_width=True, type="primary")
    if submitted:
        try:
            auth.register_student(
                username=username,
                email=email,
                full_name=full_name,
                password=password,
                confirm_password=confirm,
                recovery_question=recovery_question,
                recovery_answer=recovery_answer,
            )
            st.success("Account created. Sign in from the Login tab.")
        except ValueError as exc:
            st.error(str(exc))


def _reset() -> None:
    auth = AuthService()
    mode = st.radio("Reset method", ["Recovery question", "Reset token"], horizontal=True)
    if mode == "Recovery question":
        identity = st.text_input("Username or email", key="reset_identity")
        if st.button("Load recovery question"):
            try:
                st.session_state["recovery_question_text"] = auth.get_recovery_question(identity)
            except ValueError as exc:
                st.session_state["recovery_question_text"] = ""
                st.error(str(exc))
        question = st.session_state.get("recovery_question_text")
        if question:
            st.info(question)
            with st.form("recover_form"):
                answer = st.text_input("Recovery answer")
                new_password = st.text_input("New password", type="password")
                confirm = st.text_input("Confirm new password", type="password")
                submitted = st.form_submit_button("Reset password", use_container_width=True, type="primary")
            if submitted:
                try:
                    auth.recover_password(identity, answer, new_password, confirm)
                    st.success("Password updated. Sign in with your new password.")
                except ValueError as exc:
                    st.error(str(exc))
    else:
        identity = st.text_input("Username or email", key="token_identity")
        if st.button("Generate reset token"):
            try:
                token = auth.create_reset_token(identity)
                st.session_state["generated_reset_token"] = token
                st.success("Token generated. It expires in 1 hour.")
            except ValueError as exc:
                st.error(str(exc))
        token_value = st.session_state.get("generated_reset_token", "")
        if token_value:
            st.code(token_value)
        with st.form("token_reset_form"):
            token = st.text_input("Reset token", value=token_value)
            new_password = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            submitted = st.form_submit_button("Reset with token", use_container_width=True, type="primary")
        if submitted:
            try:
                auth.reset_with_token(token, new_password, confirm)
                st.success("Password updated. Sign in with your new password.")
            except ValueError as exc:
                st.error(str(exc))
