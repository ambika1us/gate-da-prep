from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from services.attempt_service import AttemptService
from services.user_service import UserService
from utils.helpers import format_dt, format_duration, percent, stringify_keys


def render_attempt_review(attempt: dict[str, Any], show_explanations: bool = True) -> None:
    if not attempt:
        st.warning("Attempt not found.")
        return
    stats = attempt.get("stats") or {}
    cols = st.columns(5)
    cols[0].metric("Score", f"{attempt.get('percentage') or 0:.1f}%")
    cols[1].metric("Marks", f"{attempt.get('score') or 0} / {attempt.get('total_marks') or 0}")
    cols[2].metric("Grade", attempt.get("grade") or "-")
    cols[3].metric("Time", format_duration(attempt.get("time_taken_seconds")))
    cols[4].metric("Correct", f"{stats.get('correct', 0)} / {stats.get('total', 0)}")
    st.caption(
        f"{attempt.get('exam_title', 'Exam')} · submitted {format_dt(attempt.get('submitted_at'))}"
        + (" · auto-submitted" if attempt.get("auto_submitted") else "")
    )

    category_perf = attempt.get("category_performance") or {}
    if category_perf:
        rows = [
            {
                "Category": name,
                "Obtained": values.get("obtained", 0),
                "Possible": values.get("possible", 0),
                "Efficiency": percent(values.get("obtained", 0), values.get("possible", 0)),
            }
            for name, values in category_perf.items()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    questions = attempt.get("questions") or []
    per_question = stringify_keys(attempt.get("per_question") or {})
    for idx, question in enumerate(questions, start=1):
        qid = str(question.get("_id"))
        result = per_question.get(qid, {})
        if result.get("skipped"):
            status = "Skipped"
        elif result.get("is_correct"):
            status = "Correct"
        else:
            status = "Incorrect"
        with st.expander(f"Q{idx}. {question.get('text', '')} ({status})", expanded=not result.get("is_correct")):
            st.caption(
                f"{question.get('type', '').upper()} · {question.get('difficulty')} · {question.get('marks')} marks"
            )
            options = question.get("options") or []
            selected = set(result.get("selected") or [])
            correct = set(result.get("correct") or [])
            if options:
                for opt_idx, option in enumerate(options):
                    marks = []
                    if option in selected:
                        marks.append("your answer")
                    if option in correct:
                        marks.append("correct")
                    suffix = f" — {', '.join(marks)}" if marks else ""
                    st.write(f"{chr(65 + opt_idx)}. {option}{suffix}")
            else:
                st.write(f"Your answer: {', '.join(result.get('selected') or []) or '-'}")
                st.write(f"Correct answer: {', '.join(result.get('correct') or []) or '-'}")
            st.caption(f"Earned {result.get('earned', 0)} / {question.get('marks', 0)}")
            if show_explanations and question.get("explanation"):
                st.info(question.get("explanation"))


def render_student_history(user_id: str) -> None:
    attempts = [a for a in AttemptService().list_attempts(user_id=user_id) if a.get("status") == "submitted"]
    if not attempts:
        st.info("No completed attempts yet.")
        return
    by_id = {a["_id"]: a for a in attempts}
    rows = [
        {
            "Exam": item.get("exam_title"),
            "Score": item.get("percentage"),
            "Grade": item.get("grade"),
            "Time": format_duration(item.get("time_taken_seconds")),
            "Practice": bool((item.get("exam_snapshot") or {}).get("is_practice")),
            "Submitted": format_dt(item.get("submitted_at")),
        }
        for item in attempts
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    selected_id = st.selectbox(
        "Review attempt",
        options=list(by_id.keys()),
        format_func=lambda aid: f"{by_id[aid].get('exam_title')} ({by_id[aid].get('percentage')}%)",
    )
    if selected_id:
        render_attempt_review(by_id[selected_id])


def render_admin_results() -> None:
    attempts = [a for a in AttemptService().list_attempts() if a.get("status") == "submitted"]
    users = {u["_id"]: u for u in UserService().list_users()}
    if not attempts:
        st.info("No submitted attempts yet.")
        return
    titles = sorted({a.get("exam_title") or "Exam" for a in attempts})
    exam_filter = st.selectbox("Filter by exam", options=["All"] + titles)
    filtered = [a for a in attempts if exam_filter == "All" or a.get("exam_title") == exam_filter]
    rows = []
    for item in filtered:
        user = users.get(item.get("user_id"), {})
        rows.append(
            {
                "Student": user.get("full_name") or user.get("username") or item.get("user_id"),
                "Exam": item.get("exam_title"),
                "Score": item.get("percentage"),
                "Grade": item.get("grade"),
                "Time": format_duration(item.get("time_taken_seconds")),
                "Submitted": format_dt(item.get("submitted_at")),
                "id": item.get("_id"),
            }
        )
    st.dataframe(pd.DataFrame(rows).drop(columns=["id"]), use_container_width=True, hide_index=True)
    by_id = {row["id"]: row for row in rows}
    selected_id = st.selectbox(
        "Open attempt",
        options=list(by_id.keys()),
        format_func=lambda aid: f"{by_id[aid]['Student']} · {by_id[aid]['Exam']} · {by_id[aid]['Score']}%",
    )
    if selected_id:
        attempt = AttemptService().get_by_id(selected_id)
        if attempt:
            render_attempt_review(attempt)


def time_trend_chart(attempts: list[dict[str, Any]], title: str = "Time spent per exam"):
    finished = [
        a
        for a in attempts
        if a.get("submitted_at") and a.get("status") == "submitted" and a.get("time_taken_seconds")
    ]
    if not finished:
        return None
    df = pd.DataFrame(
        {
            "Submitted": [a.get("submitted_at") for a in finished],
            "Minutes": [round(float(a.get("time_taken_seconds") or 0) / 60.0, 2) for a in finished],
            "Exam": [a.get("exam_title") or "Exam" for a in finished],
            "Score": [float(a.get("percentage") or 0) for a in finished],
        }
    ).sort_values("Submitted")
    fig = px.bar(df, x="Exam", y="Minutes", hover_data=["Score", "Submitted"], title=title)
    return fig


def score_vs_time_chart(attempts: list[dict[str, Any]], title: str = "Score vs time spent"):
    finished = [
        a
        for a in attempts
        if a.get("status") == "submitted" and a.get("time_taken_seconds")
    ]
    if not finished:
        return None
    df = pd.DataFrame(
        {
            "Minutes": [round(float(a.get("time_taken_seconds") or 0) / 60.0, 2) for a in finished],
            "Score": [float(a.get("percentage") or 0) for a in finished],
            "Exam": [a.get("exam_title") or "Exam" for a in finished],
        }
    )
    fig = px.scatter(df, x="Minutes", y="Score", hover_data=["Exam"], title=title)
    fig.update_yaxes(range=[0, 100])
    return fig


def score_trend_chart(attempts: list[dict[str, Any]], title: str = "Score trend"):
    finished = [a for a in attempts if a.get("submitted_at") and a.get("status") == "submitted"]
    if not finished:
        return None
    df = pd.DataFrame(
        {
            "Submitted": [a.get("submitted_at") for a in finished],
            "Score": [float(a.get("percentage") or 0) for a in finished],
            "Exam": [a.get("exam_title") or "Exam" for a in finished],
        }
    ).sort_values("Submitted")
    fig = px.line(df, x="Submitted", y="Score", markers=True, hover_data=["Exam"], title=title)
    fig.update_yaxes(range=[0, 100])
    return fig


def category_chart(attempts: list[dict[str, Any]]):
    buckets: dict[str, dict[str, float]] = {}
    for attempt in attempts:
        for name, values in (attempt.get("category_performance") or {}).items():
            bucket = buckets.setdefault(name, {"obtained": 0.0, "possible": 0.0})
            bucket["obtained"] += float(values.get("obtained") or 0)
            bucket["possible"] += float(values.get("possible") or 0)
    if not buckets:
        return None
    rows = [
        {"Category": name, "Efficiency": percent(vals["obtained"], vals["possible"])}
        for name, vals in buckets.items()
    ]
    return px.bar(pd.DataFrame(rows), x="Category", y="Efficiency", title="Category proficiency")


def difficulty_chart(attempts: list[dict[str, Any]]):
    buckets = {"Easy": [], "Medium": [], "Hard": []}
    for attempt in attempts:
        per_question = stringify_keys(attempt.get("per_question") or {})
        questions = {str(q.get("_id")): q for q in (attempt.get("questions") or [])}
        for qid, result in per_question.items():
            question = questions.get(qid, {})
            diff = question.get("difficulty") or "Medium"
            if diff not in buckets:
                diff = "Medium"
            if not result.get("skipped"):
                buckets[diff].append(1 if result.get("is_correct") else 0)
    rows = []
    for name, values in buckets.items():
        if values:
            rows.append({"Difficulty": name, "Accuracy": round(100 * sum(values) / len(values), 1)})
    if not rows:
        return None
    return px.bar(pd.DataFrame(rows), x="Difficulty", y="Accuracy", title="Accuracy by difficulty")
