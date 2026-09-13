from __future__ import annotations

from datetime import datetime
from typing import Any

from database import get_collection
from services.question_service import QuestionService, normalize_difficulty
from utils.helpers import generate_id, now_utc, stringify_id, stringify_ids, to_naive_utc

ALLOWED_STATUS = {"draft", "published", "archived"}
ALLOWED_MODE = {"random", "manual"}


class ExamService:
    def __init__(self) -> None:
        self.collection = get_collection("exams")
        self.attempts = get_collection("attempts")
        self.questions = QuestionService()

    def get_by_id(self, exam_id: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"_id": str(exam_id)}))

    def list_exams(
        self,
        status: str | None = None,
        include_practice: bool = False,
        search: str = "",
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if not include_practice:
            query["is_practice"] = {"$ne": True}
        if search:
            query["title"] = {"$regex": search.strip(), "$options": "i"}
        docs = stringify_ids(list(self.collection.find(query).sort("created_at", -1)))
        now = now_utc()
        for exam in docs:
            exam["is_open"] = self.is_open(exam, now)
            exam["is_upcoming"] = self.is_upcoming(exam, now)
            exam["question_count"] = exam.get("num_questions") or len(exam.get("question_ids") or [])
        return docs

    def list_published_for_student(self, include_upcoming: bool = True) -> list[dict[str, Any]]:
        exams = self.list_exams(status="published", include_practice=False)
        now = now_utc()
        result = []
        for exam in exams:
            if exam.get("is_practice"):
                continue
            if self.is_open(exam, now) or (include_upcoming and self.is_upcoming(exam, now)):
                result.append(exam)
        return result

    def create(self, **kwargs: Any) -> dict[str, Any]:
        payload = self._validate(kwargs)
        doc = {
            "_id": generate_id(),
            **payload,
            "created_at": now_utc(),
            "updated_at": None,
        }
        self.collection.insert_one(doc)
        return stringify_id(doc) or doc

    def update(self, exam_id: str, **kwargs: Any) -> dict[str, Any] | None:
        existing = self.get_by_id(exam_id)
        if not existing:
            raise ValueError("Exam not found.")
        payload = self._validate({**existing, **kwargs})
        payload["updated_at"] = now_utc()
        self.collection.update_one({"_id": str(exam_id)}, {"$set": payload})
        return self.get_by_id(exam_id)

    def set_status(self, exam_id: str, status: str) -> dict[str, Any] | None:
        if status not in ALLOWED_STATUS:
            raise ValueError("Status must be draft, published, or archived.")
        exam = self.get_by_id(exam_id)
        if not exam:
            raise ValueError("Exam not found.")
        if status == "published":
            self._ensure_publishable(exam)
        self.collection.update_one(
            {"_id": str(exam_id)},
            {"$set": {"status": status, "updated_at": now_utc()}},
        )
        return self.get_by_id(exam_id)

    def delete(self, exam_id: str) -> None:
        if self.attempts.count_documents({"exam_id": str(exam_id)}) > 0:
            raise ValueError("Cannot delete an exam that already has attempts. Archive it instead.")
        self.collection.delete_one({"_id": str(exam_id)})

    def is_open(self, exam: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or now_utc()
        if exam.get("status") != "published":
            return False
        start = to_naive_utc(exam.get("scheduled_from"))
        end = to_naive_utc(exam.get("scheduled_to"))
        if start and now < start:
            return False
        if end and now > end:
            return False
        return True

    def is_upcoming(self, exam: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or now_utc()
        if exam.get("status") != "published":
            return False
        start = to_naive_utc(exam.get("scheduled_from"))
        return bool(start and now < start)

    def select_questions(self, exam: dict[str, Any]) -> list[dict[str, Any]]:
        mode = exam.get("selection_mode") or "manual"
        if mode == "manual":
            questions = self.questions.get_many(exam.get("question_ids") or [])
            if not questions:
                raise ValueError("This exam has no questions.")
            return questions
        query: dict[str, Any] = {}
        categories = exam.get("categories") or []
        difficulties = [normalize_difficulty(d) for d in (exam.get("difficulties") or [])]
        if categories:
            query["category_id"] = {"$in": [str(cid) for cid in categories]}
        if difficulties:
            query["difficulty"] = {"$in": difficulties}
        pool = stringify_ids(list(self.questions.collection.find(query)))
        if not pool:
            raise ValueError("No questions match the exam filters.")
        import numpy as np

        count = int(exam.get("num_questions") or 0)
        if count < 1:
            raise ValueError("Random exams need a question count.")
        if count > len(pool):
            raise ValueError(f"Only {len(pool)} questions match the selected filters.")
        rng = np.random.default_rng()
        indexes = rng.choice(len(pool), size=count, replace=False)
        return [pool[int(i)] for i in indexes]

    def _ensure_publishable(self, exam: dict[str, Any]) -> None:
        if exam.get("selection_mode") == "manual" and not exam.get("question_ids"):
            raise ValueError("Publish requires at least one question.")
        if exam.get("selection_mode") == "random":
            self.select_questions(exam)

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        title = str(data.get("title") or "").strip()
        description = str(data.get("description") or "").strip()
        selection_mode = str(data.get("selection_mode") or "manual").strip().lower()
        status = str(data.get("status") or "draft").strip().lower()
        categories = [str(cid) for cid in (data.get("categories") or []) if str(cid)]
        difficulties = [normalize_difficulty(d) for d in (data.get("difficulties") or [])]
        question_ids = [str(qid) for qid in (data.get("question_ids") or []) if str(qid)]
        try:
            duration_minutes = int(data.get("duration_minutes") or 30)
            num_questions = int(data.get("num_questions") or len(question_ids) or 0)
            negative_fraction = float(data.get("negative_fraction") if data.get("negative_fraction") is not None else 0.33)
        except (TypeError, ValueError) as exc:
            raise ValueError("Numeric exam fields are invalid.") from exc
        scheduled_from = to_naive_utc(data.get("scheduled_from"))
        scheduled_to = to_naive_utc(data.get("scheduled_to"))
        if not title:
            raise ValueError("Exam title is required.")
        if selection_mode not in ALLOWED_MODE:
            raise ValueError("Selection mode must be random or manual.")
        if status not in ALLOWED_STATUS:
            raise ValueError("Status must be draft, published, or archived.")
        if duration_minutes < 1:
            raise ValueError("Duration must be at least 1 minute.")
        if negative_fraction < 0:
            raise ValueError("Negative fraction cannot be negative.")
        if scheduled_from and scheduled_to and scheduled_to <= scheduled_from:
            raise ValueError("Schedule end must be after start.")
        if selection_mode == "manual":
            questions = self.questions.get_many(question_ids)
            if len(questions) != len(question_ids):
                raise ValueError("One or more selected questions were not found.")
            num_questions = len(question_ids)
            if not categories:
                categories = sorted({q.get("category_id") for q in questions if q.get("category_id")})
        else:
            if num_questions < 1:
                raise ValueError("Random exams need a question count.")
            question_ids = []
        return {
            "title": title,
            "description": description,
            "selection_mode": selection_mode,
            "categories": categories,
            "difficulties": difficulties,
            "num_questions": num_questions,
            "question_ids": question_ids,
            "duration_minutes": duration_minutes,
            "allow_negative_marking": bool(data.get("allow_negative_marking", False)),
            "negative_fraction": negative_fraction,
            "randomize_options": bool(data.get("randomize_options", True)),
            "status": status,
            "scheduled_from": scheduled_from,
            "scheduled_to": scheduled_to,
            "is_practice": bool(data.get("is_practice", False)),
            "created_by": data.get("created_by"),
        }
