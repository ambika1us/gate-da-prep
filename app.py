from __future__ import annotations

import streamlit as st

from config import get_settings
from database import bootstrap, is_memory_fallback
from services.auth_service import AuthService
from services.seed_service import seed_if_empty
from ui.admin_pages import render_admin_portal
from ui.auth_pages import render_auth
from ui.student_pages import render_student_portal
from utils.session import clear_session, current_user, init_session, is_admin, is_authenticated, show_flash


def _boot() -> None:
    init_session()
    if not st.session_state.get("_booted"):
        bootstrap()
        AuthService().ensure_bootstrap_admin()
        seed_if_empty()
        st.session_state["_booted"] = True


def _sidebar() -> None:
    settings = get_settings()
    st.sidebar.title(settings.app_name)
    user = current_user()
    if user:
        st.sidebar.caption(f"{user.get('full_name') or user.get('username')} · {user.get('role')}")
        if st.sidebar.button("Sign out", use_container_width=True):
            clear_session()
            st.rerun()
    if is_memory_fallback():
        st.sidebar.warning("In-memory MongoDB fallback is active.")


def main() -> None:
    st.set_page_config(
        page_title="GATE DA Prep",
        page_icon="E",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; max-width: 1200px;}
        div[data-testid="stMetric"] {background: #EEF2FF; border-radius: 12px; padding: 0.6rem 0.8rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    _boot()
    _sidebar()
    show_flash()

    if not is_authenticated():
        render_auth()
        return

    if is_admin():
        render_admin_portal()
    else:
        render_student_portal()


main()
