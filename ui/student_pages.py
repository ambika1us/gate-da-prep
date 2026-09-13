from __future__ import annotations

from datetime import datetime

import streamlit as st

from services.achievement_service import AchievementService
from services.attempt_service import AttemptService
from services.auth_service import AuthService
from services.category_service import CategoryService
from services.exam_service import ExamService
from ui.results import (
    category_chart,
    difficulty_chart,
    render_attempt_review,
    render_student_history,
    score_trend_chart,
    score_vs_time_chart,
    time_trend_chart,
)
from utils.helpers import format_dt, format_duration, now_utc, stringify_keys
from utils.session import current_user


def _set_view(view: str) -> None:
    st.session_state["student_view"] = view


def render_student_portal() -> None:
    user = current_user() or {}
    view = st.session_state.get("student_view", "dashboard")
    st.sidebar.markdown("### Student")
    st.sidebar.caption(user.get("full_name") or user.get("username"))
    nav = {
        "Dashboard": "dashboard",
        "Take Exam": "exams",
        "Practice Mode": "practice",
        "Scheduled Exams": "scheduled",
        "My Results": "results",
        "Question Review": "review",
        "Performance Analytics": "analytics",
        "Achievements": "achievements",
        "Account": "account",
    }
    if st.session_state.get("active_attempt_id") and view != "session":
        if st.sidebar.button("Resume exam session", use_container_width=True, type="primary"):
            _set_view("session")
            st.rerun()
    for label, key in nav.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if view == key else "secondary"):
            _set_view(key)
            st.rerun()

    if view == "dashboard":
        _dashboard(user)
    elif view == "exams":
        _exam_catalog(user)
    elif view == "practice":
        _practice(user)
    elif view == "scheduled":
        _scheduled(user)
    elif view == "session":
        _exam_session(user)
    elif view == "results":
        st.markdown("## My Results")
        render_student_history(user["_id"])
    elif view == "review":
        st.markdown("## Question Review")
        render_student_history(user["_id"])
    elif view == "analytics":
        _analytics(user)
    elif view == "achievements":
        _achievements(user)
    elif view == "account":
        _account(user)


def _dashboard(user: dict) -> None:
    st.markdown(f"## Welcome, {user.get('full_name') or user.get('username')}")
    progress = AttemptService().user_progress(user["_id"])
    cols = st.columns(5)
    cols[0].metric("Exams completed", progress["attempts"])
    cols[1].metric("Average score", f"{progress['average_score']:.1f}%")
    cols[2].metric("Best score", f"{progress['best_score']:.1f}%")
    cols[3].metric("Avg time", format_duration(progress.get("average_time_seconds")))
    cols[4].metric("Total time", format_duration(progress["total_time_seconds"]))

    active = AttemptService().get_in_progress(user["_id"])
    if active:
        with st.container(border=True):
            st.write(f"**In progress:** {active.get('exam_title')}")
            elapsed = None
            started_at = active.get("started_at")
            if started_at and not isinstance(started_at, str):
                elapsed = max((now_utc() - started_at).total_seconds(), 0)
            st.caption(
                f"Started {format_dt(started_at)} · elapsed {format_duration(elapsed) if elapsed is not None else '-'}"
            )
            if st.button("Resume exam", type="primary"):
                st.session_state["active_attempt_id"] = active["_id"]
                st.session_state["draft_answers"] = stringify_keys(active.get("answers") or {})
                _set_view("session")
                st.rerun()

    exams = [e for e in ExamService().list_published_for_student(include_upcoming=False)]
    st.markdown("### Open exams")
    if not exams:
        st.info("No exams are open right now.")
        return
    for exam in exams[:6]:
        with st.container(border=True):
            st.write(f"**{exam.get('title')}**")
            st.caption(
                f"{exam.get('duration_minutes')} min · {exam.get('question_count')} questions · "
                f"{'Negative marking on' if exam.get('allow_negative_marking') else 'No negative marking'}"
            )
            if st.button("Start", key=f"dash_start_{exam['_id']}"):
                _begin_exam(user["_id"], exam["_id"])


def _exam_catalog(user: dict) -> None:
    st.markdown("## Take Exam")
    exams = ExamService().list_published_for_student(include_upcoming=False)
    if not exams:
        st.info("No published exams are currently open.")
        return
    for exam in exams:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.write(f"**{exam.get('title')}**")
                st.write(exam.get("description") or "")
                st.caption(
                    f"{exam.get('duration_minutes')} minutes · {exam.get('question_count')} questions · "
                    f"mode {exam.get('selection_mode')} · window {format_dt(exam.get('scheduled_from'))} - {format_dt(exam.get('scheduled_to'))}"
                )
            with right:
                existing = AttemptService().get_in_progress(user["_id"], exam["_id"])
                label = "Resume" if existing else "Start exam"
                if st.button(label, key=f"take_{exam['_id']}", type="primary"):
                    if existing:
                        st.session_state["active_attempt_id"] = existing["_id"]
                        st.session_state["draft_answers"] = stringify_keys(existing.get("answers") or {})
                        _set_view("session")
                        st.rerun()
                    else:
                        _begin_exam(user["_id"], exam["_id"])


def _practice(user: dict) -> None:
    st.markdown("## Practice Mode")
    st.caption("Build a custom practice exam. Results appear immediately after submit.")
    categories = CategoryService().list_categories()
    if not categories:
        st.info("No categories are available yet.")
        return
    cat_lookup = {c["_id"]: c.get("name") for c in categories}
    with st.form("practice_form"):
        selected = st.multiselect(
            "Categories",
            options=[c["_id"] for c in categories],
            format_func=lambda cid: cat_lookup.get(cid, cid),
        )
        difficulties = st.multiselect("Difficulties", options=["Easy", "Medium", "Hard"], default=["Easy", "Medium"])
        count = st.number_input("Number of questions", min_value=1, max_value=50, value=5)
        duration = st.number_input("Duration (minutes, reporting only)", min_value=5, value=20)
        submitted = st.form_submit_button("Start practice", type="primary")
    if submitted:
        try:
            attempt = AttemptService().start_practice(
                user_id=user["_id"],
                category_ids=selected,
                difficulties=difficulties,
                num_questions=int(count),
                duration_minutes=int(duration),
            )
            st.session_state["active_attempt_id"] = attempt["_id"]
            st.session_state["draft_answers"] = {}
            _set_view("session")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _scheduled(user: dict) -> None:
    st.markdown("## Scheduled Exams")
    exams = [e for e in ExamService().list_exams(status="published") if e.get("is_upcoming")]
    if not exams:
        st.info("No upcoming exams.")
        return
    now = now_utc()
    for exam in exams:
        start = exam.get("scheduled_from")
        remaining = ""
        if isinstance(start, datetime):
            delta = start - now
            remaining = format_duration(max(delta.total_seconds(), 0))
        with st.container(border=True):
            st.write(f"**{exam.get('title')}**")
            st.write(exam.get("description") or "")
            st.caption(f"Opens {format_dt(start)} · countdown {remaining or '-'}")


def _begin_exam(user_id: str, exam_id: str) -> None:
    try:
        attempt = AttemptService().start_attempt(user_id, exam_id)
        st.session_state["active_attempt_id"] = attempt["_id"]
        st.session_state["draft_answers"] = stringify_keys(attempt.get("answers") or {})
        _set_view("session")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


def _widget_key(attempt_id: str, question_id: str) -> str:
    return f"ans_{attempt_id}_{question_id}"


def _exam_session(user: dict) -> None:
    st.markdown("## Exam Session")
    service = AttemptService()
    attempt_id = st.session_state.get("active_attempt_id")
    attempt = service.get_by_id(attempt_id) if attempt_id else service.get_in_progress(user["_id"])
    if not attempt:
        st.info("Select an exam from Take Exam to begin.")
        return
    st.session_state["active_attempt_id"] = attempt["_id"]
    if attempt.get("status") == "submitted":
        st.success("This attempt has been submitted.")
        render_attempt_review(attempt)
        if st.button("Back to results"):
            st.session_state["active_attempt_id"] = None
            st.session_state["draft_answers"] = {}
            _set_view("results")
            st.rerun()
        return

    questions = attempt.get("questions") or []
    saved = stringify_keys(attempt.get("answers") or {})
    draft = stringify_keys(st.session_state.get("draft_answers") or saved)
    answered = 0
    for question in questions:
        qid = str(question.get("_id"))
        value = draft.get(qid)
        if isinstance(value, list):
            if value:
                answered += 1
        elif value not in (None, "", []):
            answered += 1
    st.progress(answered / max(len(questions), 1))
    st.caption(f"Answered {answered} / {len(questions)}")
    snapshot = attempt.get("exam_snapshot") or {}
    started_at = attempt.get("started_at")
    elapsed = 0
    if started_at and not isinstance(started_at, str):
        elapsed = max((now_utc() - started_at).total_seconds(), 0)
    st.write(f"**{attempt.get('exam_title')}**")
    st.caption(
        f"Time spent {format_duration(elapsed)} · planned {snapshot.get('duration_minutes', '-')} min · "
        f"{'Negative marking on' if snapshot.get('allow_negative_marking') else 'No negative marking'}"
    )

    collected: dict[str, object] = {}
    with st.form("exam_session_form"):
        for idx, question in enumerate(questions, start=1):
            qid = str(question.get("_id"))
            options = question.get("options") or []
            q_type = question.get("type") or "mcq"
            with st.container(border=True):
                st.write(f"**Q{idx}. {question.get('text')}**")
                st.caption(f"{q_type.upper()} · {question.get('difficulty')} · {question.get('marks')} marks")
                key = _widget_key(attempt["_id"], qid)
                if q_type == "mcq":
                    current = draft.get(qid)
                    radio_options = [f"{chr(65 + i)}. {opt}" for i, opt in enumerate(options)]
                    default_idx = None
                    if current in options:
                        default_idx = options.index(current)
                    choice = st.radio(
                        "Choose one answer",
                        options=radio_options,
                        index=default_idx,
                        key=key,
                    )
                    collected[qid] = options[radio_options.index(choice)] if choice else ""
                elif q_type == "msq":
                    current = draft.get(qid) or []
                    if not isinstance(current, list):
                        current = [current] if current else []
                    st.caption("Select all that apply")
                    selected = []
                    for opt_idx, option in enumerate(options):
                        checked = st.checkbox(
                            f"{chr(65 + opt_idx)}. {option}",
                            value=option in current,
                            key=f"{key}_{opt_idx}",
                        )
                        if checked:
                            selected.append(option)
                    collected[qid] = selected
                else:
                    current = draft.get(qid) or ""
                    if isinstance(current, list):
                        current = current[0] if current else ""
                    collected[qid] = st.text_input("Enter your answer", value=str(current), key=key)
        save_clicked = st.form_submit_button("Save & Resume Later")
        submit_clicked = st.form_submit_button("Submit Exam", type="primary")

    if save_clicked:
        service.save_answers(attempt["_id"], collected)
        st.session_state["draft_answers"] = collected
        st.toast("Progress saved. You can resume later.")
        st.success("Progress saved.")
    if submit_clicked:
        graded = service.submit(attempt["_id"], collected)
        st.session_state["active_attempt_id"] = graded["_id"]
        st.session_state["draft_answers"] = {}
        st.toast("Exam submitted.")
        st.rerun()


def _analytics(user: dict) -> None:
    st.markdown("## Performance Analytics")
    progress = AttemptService().user_progress(user["_id"])
    attempts = progress.get("all") or []
    cols = st.columns(5)
    cols[0].metric("Attempts", progress["attempts"])
    cols[1].metric("Average", f"{progress['average_score']:.1f}%")
    cols[2].metric("Best", f"{progress['best_score']:.1f}%")
    cols[3].metric("Avg time", format_duration(progress.get("average_time_seconds")))
    cols[4].metric("Study time", format_duration(progress["total_time_seconds"]))
    fig = score_trend_chart(attempts)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    time_fig = time_trend_chart(attempts)
    if time_fig is not None:
        st.plotly_chart(time_fig, use_container_width=True)
    scatter = score_vs_time_chart(attempts)
    if scatter is not None:
        st.plotly_chart(scatter, use_container_width=True)
    cat_fig = category_chart(attempts)
    if cat_fig is not None:
        st.plotly_chart(cat_fig, use_container_width=True)
    diff_fig = difficulty_chart(attempts)
    if diff_fig is not None:
        st.plotly_chart(diff_fig, use_container_width=True)
    if not attempts:
        st.info("Complete an exam to see analytics.")


def _achievements(user: dict) -> None:
    st.markdown("## Achievements")
    items = AchievementService().list_for_user(user["_id"])
    cols = st.columns(2)
    for idx, item in enumerate(items):
        with cols[idx % 2].container(border=True):
            status = "Earned" if item.get("earned") else "Locked"
            st.write(f"**{item.get('icon')} {item.get('name')}** · {status}")
            st.caption(item.get("criteria"))


def _account(user: dict) -> None:
    st.markdown("## Account")
    st.write(f"**Name:** {user.get('full_name')}")
    st.write(f"**Username:** {user.get('username')}")
    st.write(f"**Email:** {user.get('email')}")
    st.write(f"**Role:** {user.get('role')}")
    auth = AuthService()
    with st.form("change_password_form"):
        current = st.text_input("Current password", type="password")
        new_password = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password")
    if submitted:
        try:
            auth.change_password(user["_id"], current, new_password, confirm)
            st.success("Password updated.")
        except ValueError as exc:
            st.error(str(exc))
