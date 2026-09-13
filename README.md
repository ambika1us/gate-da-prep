# GATE DA Prep

Online examination system built with Python, Streamlit, and MongoDB.

## Features

- Role-based authentication for admins and students
- MCQ, MSQ, and NAT questions with letter-or-value correct answers
- Random or manual exam construction, practice mode, and scheduled exams
- Negative marking, partial MSQ credit, and A-F grades
- Attempt review, analytics, CSV/Excel export, and on-demand achievements
- Save and resume later; no auto-save and no countdown timer during the exam

## Architecture

```
Exam_System/
├── app.py
├── config.py
├── database.py
├── services/
├── ui/
├── utils/
└── scripts/
```

UI never talks to MongoDB directly. Pages call services; services own validation, grading, and persistence.

## Collections

- `users`
- `categories`
- `questions`
- `exams`
- `attempts`
- `password_resets`

## Setup

Full local-run, MongoDB, reverse-proxy, Streamlit Cloud, VM, and Docker instructions: `docs/LOCAL_AND_DEPLOY.md`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
python scripts/bootstrap_admin.py
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Reset the database (admin only, no sample data):

```bash
python scripts/reset_and_create.py "DELETE ALL"
```

If MongoDB is unreachable, the app falls back to an in-memory MongoDB-compatible store.

## Configuration

| Variable | Purpose |
| --- | --- |
| `MONGO_URI` | MongoDB connection string |
| `MONGO_DB` | Database name (`examadmin`) |
| `APP_NAME` | Sidebar title |
| `ADMIN_USERNAME` | Bootstrap admin username |
| `ADMIN_PASSWORD` | Bootstrap admin password |
| `SEED_DEMO` | Load sample categories, questions, and exams |

Local values live in `.env`. Deployment values live in `.streamlit/secrets.toml`.
