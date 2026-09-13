from __future__ import annotations

from typing import Any

from database import get_collection
from utils.helpers import generate_id, now_utc, stringify_id, stringify_ids


class CategoryService:
    def __init__(self) -> None:
        self.collection = get_collection("categories")
        self.questions = get_collection("questions")
        self.exams = get_collection("exams")

    def list_categories(self) -> list[dict[str, Any]]:
        docs = stringify_ids(list(self.collection.find({}).sort("name", 1)))
        for item in docs:
            item["question_count"] = self.questions.count_documents({"category_id": item["_id"]})
            item["exam_count"] = self.exams.count_documents({"categories": item["_id"]})
        return docs

    def get_by_id(self, category_id: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"_id": str(category_id)}))

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        return stringify_id(self.collection.find_one({"name": (name or "").strip()}))

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("Category name is required.")
        if self.get_by_name(name):
            raise ValueError("A category with this name already exists.")
        doc = {
            "_id": generate_id(),
            "name": name,
            "description": (description or "").strip(),
            "created_at": now_utc(),
        }
        self.collection.insert_one(doc)
        return stringify_id(doc) or doc

    def update(self, category_id: str, name: str, description: str) -> dict[str, Any] | None:
        name = (name or "").strip()
        if not name:
            raise ValueError("Category name is required.")
        existing = self.get_by_name(name)
        if existing and existing["_id"] != category_id:
            raise ValueError("A category with this name already exists.")
        self.collection.update_one(
            {"_id": str(category_id)},
            {"$set": {"name": name, "description": (description or "").strip()}},
        )
        return self.get_by_id(category_id)

    def delete(self, category_id: str) -> None:
        if self.questions.count_documents({"category_id": str(category_id)}) > 0:
            raise ValueError("Cannot delete a category that still has questions.")
        if self.exams.count_documents({"categories": str(category_id)}) > 0:
            raise ValueError("Cannot delete a category that is used by an exam.")
        self.collection.delete_one({"_id": str(category_id)})
