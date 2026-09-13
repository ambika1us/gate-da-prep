from __future__ import annotations

from typing import Any

import numpy as np

from database import get_collection
from services.category_service import CategoryService
from services.exam_service import ExamService
from services.question_service import QuestionService, normalize_difficulty
from utils.helpers import (
    generate_id,
    grade_from_percentage,
    letter_to_index,
    now_utc,
    percent,
    stringify_id,
    stringify_ids,
    stringify_keys,
    to_naive_utc,
)


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


class AttemptService:
    def __init__(self) -> None:
        self.collection = get_collection("attempts")
        self.exams = ExamService()
        self.questions = QuestionService()
        self.categories = CategoryService()

    def get_by_id(self, attempt_id: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"_id": str(attempt_id)}))

    def list_attempts(
        self,
        user_id: str | None = None,
        exam_id: str | None = None,
        status: str | None = None,
        include_practice: bool = True,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if user_id:
            query["user_id"] = str(user_id)
        if exam_id:
            query["exam_id"] = str(exam_id)
        if status:
            query["status"] = status
        docs = stringify_ids(list(self.collection.find(query).sort("started_at", -1)))
        if not include_practice:
            docs = [d for d in docs if not (d.get("exam_snapshot") or {}).get("is_practice")]
        return docs

    def get_in_progress(self, user_id: str, exam_id: str | None = None) -> dict[str, Any] | None:
        query: dict[str, Any] = {"user_id": str(user_id), "status": "in_progress"}
        if exam_id:
            query["exam_id"] = str(exam_id)
        return stringify_id(self.collection.find_one(query, sort=[("started_at", -1)]))

    def start_attempt(self, user_id: str, exam_id: str) -> dict[str, Any]:
        exam = self.exams.get_by_id(exam_id)
        if not exam:
            raise ValueError("Exam not found.")
        existing = self.get_in_progress(user_id, exam_id)
        if existing:
            return existing
        if not exam.get("is_practice") and not self.exams.is_open(exam):
            raise ValueError("This exam is not currently available.")
        questions = self.exams.select_questions(exam)
        rng = np.random.default_rng()
        prepared = []
        for question in questions:
            snapshot = dict(question)
            options = list(snapshot.get("options") or [])
            if exam.get("randomize_options") and snapshot.get("type") in {"mcq", "msq"} and len(options) > 1:
                rng.shuffle(options)
                snapshot["options"] = options
            prepared.append(snapshot)
        doc = {
            "_id": generate_id(),
            "exam_id": exam["_id"],
            "exam_title": exam.get("title"),
            "exam_snapshot": exam,
            "user_id": str(user_id),
            "status": "in_progress",
            "question_ids": [q["_id"] for q in prepared],
            "questions": prepared,
            "answers": {},
            "started_at": now_utc(),
            "submitted_at": None,
            "time_taken_seconds": None,
            "auto_submitted": False,
            "score": None,
            "total_marks": None,
            "percentage": None,
            "grade": None,
            "category_performance": {},
            "per_question": {},
            "stats": {"correct": 0, "incorrect": 0, "skipped": 0, "total": len(prepared)},
        }
        self.collection.insert_one(doc)
        return stringify_id(doc) or doc

    def start_practice(
        self,
        user_id: str,
        category_ids: list[str],
        difficulties: list[str],
        num_questions: int,
        duration_minutes: int = 30,
    ) -> dict[str, Any]:
        if not category_ids:
            raise ValueError("Select at least one category.")
        if num_questions < 1:
            raise ValueError("Choose at least one question.")
        exam = self.exams.create(
            title="Practice Session",
            description="Custom practice exam",
            selection_mode="random",
            categories=category_ids,
            difficulties=difficulties,
            num_questions=num_questions,
            duration_minutes=duration_minutes,
            allow_negative_marking=False,
            negative_fraction=0,
            randomize_options=True,
            status="published",
            is_practice=True,
            created_by=user_id,
        )
        return self.start_attempt(user_id, exam["_id"])

    def save_answers(self, attempt_id: str, answers: dict[str, Any]) -> dict[str, Any] | None:
        attempt = self.get_by_id(attempt_id)
        if not attempt:
            raise ValueError("Attempt not found.")
        if attempt.get("status") != "in_progress":
            return attempt
        safe_answers = stringify_keys(answers)
        valid_ids = {str(qid) for qid in (attempt.get("question_ids") or [])}
        filtered = {qid: value for qid, value in safe_answers.items() if qid in valid_ids}
        self.collection.update_one({"_id": str(attempt_id)}, {"$set": {"answers": filtered}})
        return self.get_by_id(attempt_id)

    def submit(self, attempt_id: str, answers: dict[str, Any] | None = None, auto_submitted: bool = False) -> dict[str, Any]:
        attempt = self.get_by_id(attempt_id)
        if not attempt:
            raise ValueError("Attempt not found.")
        if answers is not None:
            attempt = self.save_answers(attempt_id, answers) or attempt
        if attempt.get("status") == "submitted":
            return attempt
        return self._grade(attempt, auto_submitted=auto_submitted)

    def user_progress(self, user_id: str) -> dict[str, Any]:
        attempts = [a for a in self.list_attempts(user_id=user_id) if a.get("status") == "submitted"]
        official = [a for a in attempts if not (a.get("exam_snapshot") or {}).get("is_practice")]
        scores = [float(a.get("percentage") or 0) for a in official]
        time_taken = [float(a.get("time_taken_seconds") or 0) for a in official if a.get("time_taken_seconds")]
        all_time = [float(a.get("time_taken_seconds") or 0) for a in attempts if a.get("time_taken_seconds")]
        return {
            "attempts": len(official),
            "practice_attempts": len(attempts) - len(official),
            "average_score": round(float(np.mean(scores)) if scores else 0.0, 2),
            "best_score": round(max(scores), 2) if scores else 0.0,
            "total_time_seconds": round(sum(all_time), 1),
            "average_time_seconds": round(float(np.mean(time_taken)) if time_taken else 0.0, 1),
            "fastest_time_seconds": round(min(time_taken), 1) if time_taken else 0.0,
            "recent": attempts[:20],
            "all": attempts,
        }

    def analytics_overview(self) -> dict[str, Any]:
        attempts = [a for a in self.list_attempts(status="submitted") if not (a.get("exam_snapshot") or {}).get("is_practice")]
        scores = [float(a.get("percentage") or 0) for a in attempts]
        times = [float(a.get("time_taken_seconds") or 0) for a in attempts if a.get("time_taken_seconds")]
        return {
            "total_attempts": len(attempts),
            "average_score": round(float(np.mean(scores)) if scores else 0.0, 2),
            "users": len({a.get("user_id") for a in attempts}),
            "average_time_seconds": round(float(np.mean(times)) if times else 0.0, 1),
            "total_time_seconds": round(sum(times), 1),
        }

    def exam_analytics(self, exam_id: str) -> dict[str, Any]:
        attempts = [a for a in self.list_attempts(exam_id=exam_id, status="submitted")]
        scores = [float(a.get("percentage") or 0) for a in attempts]
        times = [float(a.get("time_taken_seconds") or 0) for a in attempts if a.get("time_taken_seconds")]
        question_stats: dict[str, dict[str, Any]] = {}
        for attempt in attempts:
            questions = {str(q.get("_id")): q for q in (attempt.get("questions") or [])}
            for qid, result in stringify_keys(attempt.get("per_question") or {}).items():
                question = questions.get(str(qid), {})
                bucket = question_stats.setdefault(
                    str(qid),
                    {"question_id": str(qid), "text": question.get("text", ""), "correct": 0, "total": 0},
                )
                bucket["total"] += 1
                if result.get("is_correct"):
                    bucket["correct"] += 1
        hardest = []
        for bucket in question_stats.values():
            bucket["accuracy"] = percent(bucket["correct"], bucket["total"])
            hardest.append(bucket)
        hardest.sort(key=lambda row: (row["accuracy"], -row["total"]))
        return {
            "attempts": len(attempts),
            "average_score": round(float(np.mean(scores)) if scores else 0.0, 2),
            "highest_score": round(max(scores), 2) if scores else 0.0,
            "lowest_score": round(min(scores), 2) if scores else 0.0,
            "hardest_questions": hardest[:10],
            "scores": scores,
            "times": times,
            "average_time_seconds": round(float(np.mean(times)) if times else 0.0, 1),
            "fastest_time_seconds": round(min(times), 1) if times else 0.0,
            "slowest_time_seconds": round(max(times), 1) if times else 0.0,
        }

    def export_attempt_rows(self) -> list[dict[str, Any]]:
        rows = []
        for item in self.list_attempts():
            rows.append(
                {
                    "id": item.get("_id"),
                    "exam_title": item.get("exam_title"),
                    "user_id": item.get("user_id"),
                    "status": item.get("status"),
                    "percentage": item.get("percentage"),
                    "grade": item.get("grade"),
                    "score": item.get("score"),
                    "total_marks": item.get("total_marks"),
                    "started_at": item.get("started_at"),
                    "submitted_at": item.get("submitted_at"),
                    "time_taken_seconds": item.get("time_taken_seconds"),
                    "avg_seconds_per_question": item.get("avg_seconds_per_question"),
                    "auto_submitted": item.get("auto_submitted"),
                }
            )
        return rows

    def _grade(self, attempt: dict[str, Any], auto_submitted: bool = False) -> dict[str, Any]:
        exam = attempt.get("exam_snapshot") or {}
        answers = stringify_keys(attempt.get("answers") or {})
        questions = attempt.get("questions") or []
        category_names = {c["_id"]: c.get("name", "Unknown") for c in self.categories.list_categories()}
        per_question: dict[str, dict[str, Any]] = {}
        category_performance: dict[str, dict[str, float]] = {}
        earned_total = 0.0
        possible_total = 0.0
        correct = 0
        incorrect = 0
        skipped = 0
        for question in questions:
            qid = str(question.get("_id"))
            result = self._grade_question(question, answers.get(qid), exam)
            per_question[qid] = result
            earned_total += result["earned"]
            possible_total += float(question.get("marks") or 0)
            if result["skipped"]:
                skipped += 1
            elif result["is_correct"]:
                correct += 1
            else:
                incorrect += 1
            cat_id = str(question.get("category_id") or "unknown")
            cat_name = category_names.get(cat_id, cat_id)
            bucket = category_performance.setdefault(cat_name, {"obtained": 0.0, "possible": 0.0})
            bucket["obtained"] += result["earned"]
            bucket["possible"] += float(question.get("marks") or 0)
        percentage = percent(earned_total, possible_total)
        submitted_at = now_utc()
        started_at = to_naive_utc(attempt.get("started_at")) or submitted_at
        time_taken = round(max((submitted_at - started_at).total_seconds(), 0), 1)
        question_count = max(len(questions), 1)
        updates = {
            "status": "submitted",
            "submitted_at": submitted_at,
            "time_taken_seconds": time_taken,
            "avg_seconds_per_question": round(time_taken / question_count, 1),
            "auto_submitted": bool(auto_submitted),
            "score": round(earned_total, 4),
            "total_marks": round(possible_total, 4),
            "percentage": percentage,
            "grade": grade_from_percentage(percentage),
            "category_performance": category_performance,
            "per_question": per_question,
            "stats": {
                "correct": correct,
                "incorrect": incorrect,
                "skipped": skipped,
                "total": len(questions),
            },
        }
        self.collection.update_one({"_id": str(attempt["_id"])}, {"$set": updates})
        return self.get_by_id(attempt["_id"]) or {**attempt, **updates}

    def _grade_question(self, question: dict[str, Any], raw_answer: Any, exam: dict[str, Any]) -> dict[str, Any]:
        q_type = question.get("type") or "mcq"
        marks = float(question.get("marks") or 1)
        negative_fraction = float(exam.get("negative_fraction") or 0)
        allow_negative = bool(exam.get("allow_negative_marking"))
        correct_values = [str(x) for x in (question.get("correct_answers") or [])]
        options = list(question.get("options") or [])
        selected = self._normalize_student_answer(q_type, raw_answer, options)
        skipped = len(selected) == 0
        earned = 0.0
        is_correct = False
        if q_type == "mcq":
            if skipped:
                earned = 0.0
            elif selected == correct_values:
                earned = marks
                is_correct = True
            elif allow_negative:
                earned = -marks * negative_fraction
        elif q_type == "msq":
            if skipped:
                earned = 0.0
            else:
                selected_set = set(selected)
                correct_set = set(correct_values)
                if selected_set == correct_set:
                    earned = marks
                    is_correct = True
                elif selected_set and selected_set.issubset(correct_set):
                    earned = marks * (len(selected_set) / max(len(correct_set), 1))
                else:
                    earned = 0.0
        elif q_type == "nat":
            if skipped:
                earned = 0.0
            else:
                try:
                    given = float(selected[0])
                    target = float(correct_values[0])
                    tolerance = max(0.0001, abs(target) * 0.001)
                    if abs(given - target) <= tolerance:
                        earned = marks
                        is_correct = True
                    elif allow_negative:
                        earned = -marks * negative_fraction
                except (TypeError, ValueError, IndexError):
                    earned = -marks * negative_fraction if allow_negative else 0.0
        return {
            "earned": round(earned, 4),
            "is_correct": is_correct,
            "skipped": skipped,
            "selected": selected,
            "correct": correct_values,
        }

    def _normalize_student_answer(self, q_type: str, raw_answer: Any, options: list[str]) -> list[str]:
        values = _as_list(raw_answer)
        if q_type == "nat":
            return values[:1]
        resolved = []
        for item in values:
            if item in options:
                resolved.append(item)
                continue
            letter_idx = letter_to_index(item)
            if letter_idx is not None and letter_idx < len(options):
                resolved.append(options[letter_idx])
                continue
            if item.isdigit():
                idx = int(item)
                if 0 <= idx < len(options):
                    resolved.append(options[idx])
                    continue
            resolved.append(item)
        unique: list[str] = []
        for item in resolved:
            if item not in unique:
                unique.append(item)
        return unique
