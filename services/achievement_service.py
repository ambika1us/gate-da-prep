from __future__ import annotations

from datetime import timedelta
from typing import Any

from database import get_collection
from utils.helpers import now_utc

ACHIEVEMENT_CATALOG = [
    {"id": "first_exam", "name": "First Steps", "icon": "1", "criteria": "Complete 1 exam"},
    {"id": "ten_exams", "name": "Marathoner", "icon": "10", "criteria": "Complete 10 exams"},
    {"id": "score_90", "name": "Top Scorer", "icon": "90", "criteria": "Score 90% or higher"},
    {"id": "perfect", "name": "Sharpshooter", "icon": "100", "criteria": "Score 100%"},
    {"id": "three_categories", "name": "Explorer", "icon": "3", "criteria": "Attempt 3+ categories"},
    {"id": "five_in_week", "name": "On Fire", "icon": "5", "criteria": "5 exams in 7 days"},
    {"id": "practice_mode", "name": "Dedicated", "icon": "P", "criteria": "Complete a practice exam"},
    {"id": "analytics_pro", "name": "Data Scientist", "icon": "A", "criteria": "10+ attempts with analytics"},
]


class AchievementService:
    def __init__(self) -> None:
        self.attempts = get_collection("attempts")

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        attempts = list(
            self.attempts.find({"user_id": str(user_id), "status": "submitted"}).sort("submitted_at", -1)
        )
        official = [a for a in attempts if not (a.get("exam_snapshot") or {}).get("is_practice")]
        practice = [a for a in attempts if (a.get("exam_snapshot") or {}).get("is_practice")]
        scores = [float(a.get("percentage") or 0) for a in official]
        categories: set[str] = set()
        for attempt in attempts:
            for question in attempt.get("questions") or []:
                if question.get("category_id"):
                    categories.add(str(question["category_id"]))
        week_cutoff = now_utc() - timedelta(days=7)
        recent_week = 0
        for attempt in official:
            submitted = attempt.get("submitted_at")
            if submitted and submitted >= week_cutoff:
                recent_week += 1

        checks = {
            "first_exam": len(official) >= 1,
            "ten_exams": len(official) >= 10,
            "score_90": any(score >= 90 for score in scores),
            "perfect": any(score >= 100 for score in scores),
            "three_categories": len(categories) >= 3,
            "five_in_week": recent_week >= 5,
            "practice_mode": len(practice) >= 1,
            "analytics_pro": len(attempts) >= 10,
        }
        catalog = []
        for item in ACHIEVEMENT_CATALOG:
            row = dict(item)
            row["earned"] = bool(checks.get(item["id"]))
            catalog.append(row)
        return catalog
