from __future__ import annotations

import csv
import io
from typing import Any

from database import get_collection
from utils.helpers import generate_id, letter_to_index, now_utc, stringify_id, stringify_ids

ALLOWED_TYPES = {"mcq", "msq", "nat"}
ALLOWED_DIFFICULTY = {"Easy", "Medium", "Hard"}


def normalize_difficulty(value: str) -> str:
    mapping = {
        "easy": "Easy",
        "medium": "Medium",
        "hard": "Hard",
    }
    raw = (value or "Medium").strip()
    return mapping.get(raw.lower(), raw if raw in ALLOWED_DIFFICULTY else "Medium")


def normalize_type(value: str) -> str:
    mapping = {
        "single": "mcq",
        "multiple": "msq",
        "true_false": "mcq",
        "numerical": "nat",
    }
    raw = (value or "mcq").strip().lower()
    return mapping.get(raw, raw if raw in ALLOWED_TYPES else "mcq")


class QuestionService:
    def __init__(self) -> None:
        self.collection = get_collection("questions")
        self.exams = get_collection("exams")

    def get_by_id(self, question_id: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"_id": str(question_id)}))

    def list_questions(
        self,
        category_id: str | None = None,
        difficulty: str | None = None,
        q_type: str | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if category_id:
            query["category_id"] = str(category_id)
        if difficulty:
            query["difficulty"] = normalize_difficulty(difficulty)
        if q_type:
            query["type"] = normalize_type(q_type)
        if search:
            query["text"] = {"$regex": search.strip(), "$options": "i"}
        docs = list(self.collection.find(query).sort("created_at", -1))
        return stringify_ids(docs)

    def get_many(self, question_ids: list[str]) -> list[dict[str, Any]]:
        ids = [str(qid) for qid in question_ids or []]
        if not ids:
            return []
        docs = stringify_ids(list(self.collection.find({"_id": {"$in": ids}})))
        by_id = {doc["_id"]: doc for doc in docs}
        return [by_id[qid] for qid in ids if qid in by_id]

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

    def update(self, question_id: str, **kwargs: Any) -> dict[str, Any] | None:
        existing = self.get_by_id(question_id)
        if not existing:
            raise ValueError("Question not found.")
        merged = {**existing, **kwargs}
        if "text" not in kwargs and "prompt" not in kwargs:
            merged["text"] = existing.get("text") or existing.get("prompt")
        payload = self._validate(merged)
        payload["updated_at"] = now_utc()
        self.collection.update_one({"_id": str(question_id)}, {"$set": payload})
        return self.get_by_id(question_id)

    def delete(self, question_id: str) -> None:
        in_exam = self.exams.count_documents({"question_ids": str(question_id)})
        if in_exam:
            raise ValueError("Cannot delete a question assigned to an exam.")
        self.collection.delete_one({"_id": str(question_id)})

    def count(self, category_id: str | None = None) -> int:
        query: dict[str, Any] = {}
        if category_id:
            query["category_id"] = str(category_id)
        return self.collection.count_documents(query)

    def export_rows(self, questions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        items = questions if questions is not None else self.list_questions()
        rows = []
        for item in items:
            rows.append(
                {
                    "id": item.get("_id"),
                    "category_id": item.get("category_id"),
                    "type": item.get("type"),
                    "text": item.get("text"),
                    "options": " | ".join(item.get("options") or []),
                    "correct_answers": " | ".join(str(x) for x in (item.get("correct_answers") or [])),
                    "difficulty": item.get("difficulty"),
                    "explanation": item.get("explanation", ""),
                    "marks": item.get("marks"),
                }
            )
        return rows

    def import_csv(self, raw: str, default_category_id: str = "") -> int:
        reader = csv.DictReader(io.StringIO(raw))
        created = 0
        for row in reader:
            options = [part.strip() for part in (row.get("options") or "").split("|") if part.strip()]
            answers = [part.strip() for part in (row.get("correct_answers") or "").split("|") if part.strip()]
            self.create(
                text=row.get("text") or row.get("prompt") or "",
                q_type=row.get("type") or "mcq",
                options=options,
                correct_answers=answers,
                category_id=row.get("category_id") or default_category_id,
                difficulty=row.get("difficulty") or "Medium",
                explanation=row.get("explanation") or "",
                marks=row.get("marks") or 1,
            )
            created += 1
        return created

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        text = str(data.get("text") or data.get("prompt") or "").strip()
        q_type = normalize_type(str(data.get("type") or data.get("q_type") or "mcq"))
        difficulty = normalize_difficulty(str(data.get("difficulty") or "Medium"))
        category_id = str(data.get("category_id") or "").strip()
        explanation = str(data.get("explanation") or "").strip()
        try:
            marks = float(data.get("marks") if data.get("marks") is not None else data.get("points") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("Marks must be a number.") from exc
        options = [str(opt).strip() for opt in (data.get("options") or []) if str(opt).strip()]
        raw_answers = data.get("correct_answers") or []
        if isinstance(raw_answers, str):
            raw_answers = [raw_answers]
        answers = [str(item).strip() for item in raw_answers if str(item).strip()]
        answers = self._canonicalize_answers(q_type, options, answers)

        if not text:
            raise ValueError("Question text is required.")
        if q_type not in ALLOWED_TYPES:
            raise ValueError("Question type must be mcq, msq, or nat.")
        if difficulty not in ALLOWED_DIFFICULTY:
            raise ValueError("Difficulty must be Easy, Medium, or Hard.")
        if not category_id:
            raise ValueError("Category is required.")
        if marks <= 0:
            raise ValueError("Marks must be greater than 0.")
        if q_type in {"mcq", "msq"} and len(options) < 2:
            raise ValueError("At least two options are required.")
        if q_type == "mcq" and len(answers) != 1:
            raise ValueError("MCQ questions must have exactly one correct answer.")
        if q_type == "msq" and len(answers) < 2:
            raise ValueError("MSQ questions must have at least two correct answers.")
        if q_type == "nat" and len(answers) != 1:
            raise ValueError("NAT questions must have exactly one numeric answer.")
        if q_type == "nat":
            options = []
            try:
                float(answers[0])
            except ValueError as exc:
                raise ValueError("NAT correct answer must be numeric.") from exc

        return {
            "category_id": category_id,
            "type": q_type,
            "text": text,
            "options": options,
            "correct_answers": answers,
            "difficulty": difficulty,
            "explanation": explanation,
            "marks": marks,
        }

    def _canonicalize_answers(self, q_type: str, options: list[str], answers: list[str]) -> list[str]:
        if q_type == "nat":
            return answers[:1]
        resolved: list[str] = []
        for item in answers:
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
            raise ValueError(f"Correct answer '{item}' does not match an option.")
        unique: list[str] = []
        for item in resolved:
            if item not in unique:
                unique.append(item)
        return unique
