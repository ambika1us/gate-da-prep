from __future__ import annotations

from datetime import timedelta

from config import get_settings
from services.auth_service import AuthService
from services.category_service import CategoryService
from services.exam_service import ExamService
from services.question_service import QuestionService
from services.user_service import UserService
from utils.helpers import now_utc


def seed_if_empty() -> dict[str, int]:
    settings = get_settings()
    auth = AuthService()
    users = UserService()
    categories = CategoryService()
    questions = QuestionService()
    exams = ExamService()
    created = {"users": 0, "categories": 0, "questions": 0, "exams": 0}

    auth.ensure_bootstrap_admin()
    if not settings.seed_demo:
        return created
    if categories.list_categories():
        return created

    if not users.get_by_username("student"):
        users.create_user(
            username="student",
            email="student@example.com",
            full_name="Alex Student",
            password="Student@123",
            role="student",
            recovery_question="What is your demo username?",
            recovery_answer="student",
        )
        created["users"] += 1

    math_cat = categories.create("Mathematics", "Quantitative aptitude and linear algebra")
    ds_cat = categories.create("Data Science", "Probability, ML, and statistics")
    py_cat = categories.create("Python", "Programming and data structures")
    created["categories"] = 3

    specs = [
        {
            "text": "What is the derivative of x^2?",
            "q_type": "mcq",
            "options": ["x", "2x", "x^2", "2"],
            "correct_answers": ["B"],
            "category_id": math_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "d/dx of x^2 is 2x.",
        },
        {
            "text": "Which of the following are even numbers?",
            "q_type": "msq",
            "options": ["2", "3", "4", "9"],
            "correct_answers": ["A", "C"],
            "category_id": math_cat["_id"],
            "difficulty": "Easy",
            "marks": 2,
            "explanation": "2 and 4 are even.",
        },
        {
            "text": "Value of 3 * 1.5",
            "q_type": "nat",
            "options": [],
            "correct_answers": ["4.5"],
            "category_id": math_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "3 multiplied by 1.5 equals 4.5.",
        },
        {
            "text": "Which metric is least sensitive to outliers?",
            "q_type": "mcq",
            "options": ["Mean", "Median", "Range", "Variance"],
            "correct_answers": ["Median"],
            "category_id": ds_cat["_id"],
            "difficulty": "Medium",
            "marks": 2,
            "explanation": "The median is robust to extreme values.",
        },
        {
            "text": "Which are supervised learning algorithms?",
            "q_type": "msq",
            "options": ["Linear Regression", "K-Means", "Decision Tree", "PCA"],
            "correct_answers": ["Linear Regression", "Decision Tree"],
            "category_id": ds_cat["_id"],
            "difficulty": "Medium",
            "marks": 2,
            "explanation": "K-Means and PCA are unsupervised.",
        },
        {
            "text": "A fair coin is tossed once. Probability of heads?",
            "q_type": "nat",
            "options": [],
            "correct_answers": ["0.5"],
            "category_id": ds_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "P(heads) = 1/2 = 0.5.",
        },
        {
            "text": "Which keyword defines a Python function?",
            "q_type": "mcq",
            "options": ["func", "def", "function", "lambda"],
            "correct_answers": ["def"],
            "category_id": py_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "Python uses def for named functions.",
        },
        {
            "text": "Which of the following are Python built-in collections?",
            "q_type": "msq",
            "options": ["list", "tuple", "arraylist", "dict"],
            "correct_answers": ["list", "tuple", "dict"],
            "category_id": py_cat["_id"],
            "difficulty": "Medium",
            "marks": 2,
            "explanation": "arraylist is not a Python built-in type.",
        },
        {
            "text": "What is the output of len([1, 2, 3])?",
            "q_type": "nat",
            "options": [],
            "correct_answers": ["3"],
            "category_id": py_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "The list has three elements.",
        },
        {
            "text": "Which statement about lists is true?",
            "q_type": "mcq",
            "options": ["Lists are immutable", "Lists are mutable", "Lists cannot nest", "Lists are unordered"],
            "correct_answers": ["B"],
            "category_id": py_cat["_id"],
            "difficulty": "Easy",
            "marks": 1,
            "explanation": "Python lists can be changed in place.",
        },
    ]
    created_questions = [questions.create(**spec) for spec in specs]
    created["questions"] = len(created_questions)

    now = now_utc()
    exams.create(
        title="Mathematics Warmup",
        description="Short GATE-style mix of MCQ, MSQ, and NAT items.",
        selection_mode="manual",
        categories=[math_cat["_id"]],
        difficulties=["Easy", "Medium"],
        question_ids=[q["_id"] for q in created_questions if q["category_id"] == math_cat["_id"]],
        duration_minutes=20,
        allow_negative_marking=True,
        negative_fraction=0.33,
        randomize_options=True,
        status="published",
        scheduled_from=now - timedelta(days=1),
        scheduled_to=now + timedelta(days=30),
        is_practice=False,
        created_by=None,
    )
    exams.create(
        title="GATE DA Mixed Set",
        description="Published mixed set across Mathematics, Data Science, and Python.",
        selection_mode="manual",
        categories=[math_cat["_id"], ds_cat["_id"], py_cat["_id"]],
        difficulties=["Easy", "Medium", "Hard"],
        question_ids=[q["_id"] for q in created_questions],
        duration_minutes=40,
        allow_negative_marking=True,
        negative_fraction=0.33,
        randomize_options=True,
        status="published",
        scheduled_from=now - timedelta(hours=2),
        scheduled_to=now + timedelta(days=45),
        is_practice=False,
        created_by=None,
    )
    exams.create(
        title="Upcoming Probability Drill",
        description="Scheduled exam that opens later.",
        selection_mode="random",
        categories=[ds_cat["_id"]],
        difficulties=["Easy", "Medium"],
        num_questions=2,
        duration_minutes=15,
        allow_negative_marking=False,
        status="published",
        scheduled_from=now + timedelta(days=3),
        scheduled_to=now + timedelta(days=10),
        is_practice=False,
        created_by=None,
    )
    created["exams"] = 3
    return created
