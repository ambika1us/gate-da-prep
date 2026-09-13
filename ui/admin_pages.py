from __future__ import annotations

from datetime import datetime, time
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

from database import is_memory_fallback
from services.attempt_service import AttemptService
from services.auth_service import AuthService
from services.category_service import CategoryService
from services.exam_service import ExamService
from services.question_service import QuestionService
from services.user_service import UserService
from ui.results import render_admin_results, score_vs_time_chart, time_trend_chart
from utils.helpers import format_dt, format_duration
from utils.session import current_user


def _set_view(view: str) -> None:
    st.session_state["admin_view"] = view


def _df_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


def render_admin_portal() -> None:
    user = current_user() or {}
    view = st.session_state.get("admin_view", "dashboard")
    st.sidebar.markdown("### Admin")
    st.sidebar.caption(user.get("full_name") or user.get("username"))
    nav = {
        "Dashboard": "dashboard",
        "Categories": "categories",
        "Questions": "questions",
        "Exams": "exams",
        "Users": "users",
        "Analytics": "analytics",
        "Export": "export",
        "Results": "results",
    }
    for label, key in nav.items():
        if st.sidebar.button(label, use_container_width=True, type="primary" if view == key else "secondary"):
            _set_view(key)
            st.rerun()

    if view == "dashboard":
        _dashboard()
    elif view == "categories":
        _categories()
    elif view == "questions":
        _questions()
    elif view == "exams":
        _exams()
    elif view == "users":
        _users()
    elif view == "analytics":
        _analytics()
    elif view == "export":
        _export()
    elif view == "results":
        st.markdown("## Results")
        render_admin_results()


def _dashboard() -> None:
    st.markdown("## Admin dashboard")
    if is_memory_fallback():
        st.warning("MongoDB is not reachable. Using an in-memory database for this session.")
    users = UserService()
    questions = QuestionService()
    exams = ExamService()
    attempts = AttemptService()
    overview = attempts.analytics_overview()
    cols = st.columns(5)
    cols[0].metric("Users", users.count())
    cols[1].metric("Questions", questions.count())
    cols[2].metric("Exams", len(exams.list_exams(include_practice=True)))
    cols[3].metric("Attempts", overview["total_attempts"])
    cols[4].metric("Avg time", format_duration(overview.get("average_time_seconds")))
    recent = attempts.list_attempts()[:10]
    if recent:
        df = pd.DataFrame(
            {
                "Exam": [a.get("exam_title") for a in recent],
                "Status": [a.get("status") for a in recent],
                "Score": [a.get("percentage") for a in recent],
                "Started": [format_dt(a.get("started_at")) for a in recent],
            }
        )
        st.dataframe(df, use_container_width=True, hide_index=True)


def _categories() -> None:
    st.markdown("## Categories")
    service = CategoryService()
    with st.form("create_category"):
        name = st.text_input("Name")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Add category")
    if submitted:
        try:
            service.create(name, description)
            st.success("Category created.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    for cat in service.list_categories():
        with st.container(border=True):
            st.write(f"**{cat.get('name')}** · {cat.get('question_count')} questions")
            st.caption(cat.get("description") or "")
            new_name = st.text_input("Rename", value=cat.get("name"), key=f"cat_name_{cat['_id']}")
            new_desc = st.text_input("Description", value=cat.get("description", ""), key=f"cat_desc_{cat['_id']}")
            c1, c2 = st.columns(2)
            if c1.button("Save", key=f"cat_save_{cat['_id']}"):
                try:
                    service.update(cat["_id"], new_name, new_desc)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if c2.button("Remove", key=f"cat_del_{cat['_id']}"):
                try:
                    service.delete(cat["_id"])
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def _questions() -> None:
    st.markdown("## Questions")
    q_service = QuestionService()
    categories = CategoryService().list_categories()
    if not categories:
        st.info("Create a category first.")
        return
    cat_lookup = {c["_id"]: c.get("name") for c in categories}
    tab_list, tab_create, tab_import = st.tabs(["Bank", "Add question", "CSV import"])
    with tab_list:
        cat_filter = st.selectbox(
            "Category filter",
            options=["All"] + [c["_id"] for c in categories],
            format_func=lambda x: "All" if x == "All" else cat_lookup.get(x, x),
        )
        difficulty = st.selectbox("Difficulty", ["All", "Easy", "Medium", "Hard"])
        q_type = st.selectbox("Type", ["All", "mcq", "msq", "nat"])
        search = st.text_input("Search text")
        items = q_service.list_questions(
            category_id=None if cat_filter == "All" else cat_filter,
            difficulty=None if difficulty == "All" else difficulty,
            q_type=None if q_type == "All" else q_type,
            search=search,
        )
        if items:
            export_df = pd.DataFrame(q_service.export_rows(items))
            st.download_button("Download filtered CSV", export_df.to_csv(index=False).encode("utf-8"), "questions.csv", "text/csv")
        for item in items:
            with st.expander(f"{item.get('text')} ({item.get('type')} · {item.get('difficulty')} · {item.get('marks')} marks)"):
                st.caption(cat_lookup.get(item.get("category_id"), "-"))
                for idx, option in enumerate(item.get("options") or []):
                    marker = " (correct)" if option in (item.get("correct_answers") or []) else ""
                    st.write(f"{chr(65 + idx)}. {option}{marker}")
                if item.get("type") == "nat":
                    st.write(f"Correct: {', '.join(item.get('correct_answers') or [])}")
                if st.button("Delete", key=f"q_del_{item['_id']}"):
                    try:
                        q_service.delete(item["_id"])
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    with tab_create:
        with st.form("create_question"):
            text = st.text_area("Question text")
            q_type = st.selectbox("Type", ["mcq", "msq", "nat"])
            difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
            category_id = st.selectbox("Category", options=[c["_id"] for c in categories], format_func=lambda x: cat_lookup.get(x, x))
            marks = st.number_input("Marks", min_value=0.5, value=1.0, step=0.5)
            explanation = st.text_area("Explanation")
            raw_options = st.text_area("Options (one per line; unused for NAT)")
            raw_answers = st.text_input("Correct answers (option text, letters A/B/C, or NAT number; use | for MSQ)")
            submitted = st.form_submit_button("Save question")
        if submitted:
            options = [line.strip() for line in raw_options.splitlines() if line.strip()]
            answers = [part.strip() for part in raw_answers.replace(",", "|").split("|") if part.strip()]
            try:
                q_service.create(
                    text=text,
                    q_type=q_type,
                    options=options,
                    correct_answers=answers,
                    category_id=category_id,
                    difficulty=difficulty,
                    marks=float(marks),
                    explanation=explanation,
                )
                st.success("Question created.")
            except ValueError as exc:
                st.error(str(exc))
    with tab_import:
        default_cat = st.selectbox("Default category", options=[c["_id"] for c in categories], format_func=lambda x: cat_lookup.get(x, x), key="import_cat")
        uploaded = st.file_uploader("CSV with columns text,type,options,correct_answers,difficulty,marks,explanation,category_id", type=["csv"])
        if uploaded is not None and st.button("Import CSV"):
            try:
                created = q_service.import_csv(uploaded.getvalue().decode("utf-8"), default_category_id=default_cat)
                st.success(f"Imported {created} questions.")
            except ValueError as exc:
                st.error(str(exc))


def _exams() -> None:
    st.markdown("## Exams")
    exam_service = ExamService()
    q_service = QuestionService()
    categories = CategoryService().list_categories()
    if not categories:
        st.info("Create a category first.")
        return
    cat_lookup = {c["_id"]: c.get("name") for c in categories}
    questions = q_service.list_questions()
    tab_list, tab_create = st.tabs(["Catalog", "Create exam"])
    with tab_list:
        exams = exam_service.list_exams(include_practice=False)
        for exam in exams:
            with st.container(border=True):
                st.write(f"**{exam.get('title')}** · {exam.get('status')}")
                st.caption(
                    f"{exam.get('selection_mode')} · {exam.get('question_count')} questions · "
                    f"{exam.get('duration_minutes')} min · negative {exam.get('allow_negative_marking')}"
                )
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("Publish", key=f"exam_pub_{exam['_id']}"):
                    try:
                        exam_service.set_status(exam["_id"], "published")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                if c2.button("Draft", key=f"exam_draft_{exam['_id']}"):
                    exam_service.set_status(exam["_id"], "draft")
                    st.rerun()
                if c3.button("Archive", key=f"exam_arch_{exam['_id']}"):
                    exam_service.set_status(exam["_id"], "archived")
                    st.rerun()
                if c4.button("Delete", key=f"exam_del_{exam['_id']}"):
                    try:
                        exam_service.delete(exam["_id"])
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    with tab_create:
        mode = st.selectbox("Selection mode", ["manual", "random"])
        with st.form("create_exam"):
            title = st.text_input("Title")
            description = st.text_area("Description")
            selected_cats = st.multiselect(
                "Categories",
                options=[c["_id"] for c in categories],
                format_func=lambda x: cat_lookup.get(x, x),
            )
            difficulties = st.multiselect("Difficulties", options=["Easy", "Medium", "Hard"], default=["Easy", "Medium", "Hard"])
            selected_qs = []
            num_questions = 5
            if mode == "manual":
                selected_qs = st.multiselect(
                    "Questions",
                    options=[q["_id"] for q in questions],
                    format_func=lambda qid: next((q.get("text", qid)[:80] for q in questions if q["_id"] == qid), qid),
                )
            else:
                num_questions = st.number_input("Number of questions", min_value=1, value=5)
            duration = st.number_input("Duration (minutes)", min_value=1, value=30)
            allow_neg = st.checkbox("Allow negative marking", value=True)
            neg_frac = st.number_input("Negative fraction", min_value=0.0, max_value=1.0, value=0.33)
            randomize = st.checkbox("Randomize options", value=True)
            status = st.selectbox("Status", ["draft", "published"])
            start_day = st.date_input("Scheduled from date")
            end_day = st.date_input("Scheduled to date")
            submitted = st.form_submit_button("Create exam")
        if submitted:
            available_from = datetime.combine(start_day, time.min)
            available_until = datetime.combine(end_day, time.max)
            try:
                exam_service.create(
                    title=title,
                    description=description,
                    selection_mode=mode,
                    categories=selected_cats,
                    difficulties=difficulties,
                    question_ids=selected_qs,
                    num_questions=int(num_questions),
                    duration_minutes=int(duration),
                    allow_negative_marking=allow_neg,
                    negative_fraction=float(neg_frac),
                    randomize_options=randomize,
                    status=status,
                    scheduled_from=available_from,
                    scheduled_to=available_until,
                    is_practice=False,
                    created_by=(current_user() or {}).get("_id"),
                )
                st.success("Exam created.")
            except ValueError as exc:
                st.error(str(exc))


def _users() -> None:
    st.markdown("## Users")
    service = UserService()
    auth = AuthService()
    tab_list, tab_create = st.tabs(["Directory", "Create user"])
    with tab_list:
        search = st.text_input("Search users")
        role = st.selectbox("Role", ["All", "student", "admin"])
        users = service.list_users(role=None if role == "All" else role, search=search)
        df = pd.DataFrame(
            [
                {
                    "Name": u.get("full_name"),
                    "Username": u.get("username"),
                    "Email": u.get("email"),
                    "Role": u.get("role"),
                    "Status": "Blocked" if u.get("blocked", False) else "Active",
                    "Last login": format_dt(u.get("last_login")),
                    "id": u.get("_id"),
                }
                for u in users
            ]
        )
        if df.empty:
            st.info("No users found.")
        else:
            st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
            by_id = {u["_id"]: u for u in users}
            selected_id = st.selectbox(
                "Manage user",
                options=list(by_id.keys()),
                format_func=lambda uid: f"{by_id[uid].get('full_name')} ({by_id[uid].get('username')})",
            )
            selected = by_id.get(selected_id)
            if selected:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    if st.button("Block" if not selected.get("blocked") else "Unblock"):
                        service.set_blocked(selected["_id"], not selected.get("blocked"))
                        st.rerun()
                with col2:
                    new_role = "admin" if selected.get("role") == "student" else "student"
                    if st.button(f"Make {new_role}"):
                        service.update_user(selected["_id"], {"role": new_role})
                        st.rerun()
                with col3:
                    reset = st.text_input("Set new password", type="password", key="admin_reset_pw")
                    if st.button("Reset password") and reset:
                        try:
                            service.set_password(selected["_id"], reset, require_strong=False)
                            st.success("Password updated.")
                        except ValueError as exc:
                            st.error(str(exc))
                with col4:
                    if st.button("Delete user"):
                        try:
                            service.delete_user(selected["_id"])
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
    with tab_create:
        with st.form("admin_create_user"):
            full_name = st.text_input("Full name")
            username = st.text_input("Username")
            email = st.text_input("Email")
            role = st.selectbox("Role", ["student", "admin"])
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            question = st.text_input("Recovery question")
            answer = st.text_input("Recovery answer")
            submitted = st.form_submit_button("Create")
        if submitted:
            try:
                if password != confirm:
                    raise ValueError("Passwords do not match.")
                if role == "student":
                    auth.register_student(username, email, full_name, password, confirm, question, answer)
                else:
                    service.create_user(username, email, full_name, password, "admin", question, answer, require_strong=False)
                st.success("User created.")
            except ValueError as exc:
                st.error(str(exc))


def _analytics() -> None:
    st.markdown("## Analytics")
    exams = ExamService().list_exams(include_practice=False)
    attempts = AttemptService().list_attempts(status="submitted")
    if attempts:
        exam_counts = pd.DataFrame(
            [
                {
                    "Exam": a.get("exam_title") or "Exam",
                    "Score": a.get("percentage") or 0,
                    "Minutes": round(float(a.get("time_taken_seconds") or 0) / 60.0, 2),
                }
                for a in attempts
            ]
        )
        st.plotly_chart(px.histogram(exam_counts, x="Score", nbins=10, title="Score distribution"), use_container_width=True)
        counts = exam_counts.groupby("Exam").size().reset_index(name="Attempts")
        st.plotly_chart(px.bar(counts, x="Exam", y="Attempts", title="Exam-wise attempts"), use_container_width=True)
        time_fig = time_trend_chart(attempts, "Average completion time by exam")
        if time_fig is not None:
            st.plotly_chart(time_fig, use_container_width=True)
        scatter = score_vs_time_chart(attempts)
        if scatter is not None:
            st.plotly_chart(scatter, use_container_width=True)
        timeline = pd.DataFrame(
            {
                "Submitted": [a.get("submitted_at") for a in attempts if a.get("submitted_at")],
                "User": [a.get("user_id") for a in attempts if a.get("submitted_at")],
            }
        )
        if not timeline.empty:
            st.plotly_chart(px.histogram(timeline, x="Submitted", title="User activity timeline"), use_container_width=True)
    if not exams:
        st.info("No exams yet.")
        return
    by_id = {e["_id"]: e for e in exams}
    selected_id = st.selectbox("Exam detail", options=list(by_id.keys()), format_func=lambda eid: by_id[eid].get("title", eid))
    stats = AttemptService().exam_analytics(selected_id)
    cols = st.columns(5)
    cols[0].metric("Attempts", stats["attempts"])
    cols[1].metric("Average", f"{stats['average_score']:.1f}%")
    cols[2].metric("High", f"{stats['highest_score']:.0f}%")
    cols[3].metric("Low", f"{stats['lowest_score']:.0f}%")
    cols[4].metric("Avg time", format_duration(stats.get("average_time_seconds")))
    hardest = stats.get("hardest_questions") or []
    if hardest:
        df = pd.DataFrame(hardest)
        st.plotly_chart(px.bar(df, x="accuracy", y="text", orientation="h", title="Question accuracy"), use_container_width=True)


def _export() -> None:
    st.markdown("## Export")
    questions = QuestionService().export_rows()
    attempts = AttemptService().export_attempt_rows()
    q_df = pd.DataFrame(questions)
    a_df = pd.DataFrame(attempts)
    st.write("Questions")
    if q_df.empty:
        st.info("No questions to export.")
    else:
        st.dataframe(q_df, use_container_width=True, hide_index=True)
        st.download_button("Questions CSV", q_df.to_csv(index=False).encode("utf-8"), "questions.csv", "text/csv")
        try:
            st.download_button("Questions Excel", _df_excel_bytes(q_df), "questions.xlsx")
        except Exception:
            st.caption("Install openpyxl for Excel export.")
    st.write("Attempts")
    if a_df.empty:
        st.info("No attempts to export.")
        return
    st.dataframe(a_df, use_container_width=True, hide_index=True)
    st.download_button("Attempts CSV", a_df.to_csv(index=False).encode("utf-8"), "attempts.csv", "text/csv")
    try:
        st.download_button("Attempts Excel", _df_excel_bytes(a_df), "attempts.xlsx")
    except Exception:
        st.caption("Install openpyxl for Excel export.")
