from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings
from database import bootstrap, get_db
from services.auth_service import AuthService


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "DELETE ALL":
        print('Refusing to reset. Re-run with: python scripts/reset_and_create.py "DELETE ALL"')
        sys.exit(1)
    bootstrap()
    db = get_db()
    for name in ("achievements", "attempts", "exams", "questions", "categories", "users", "password_resets"):
        db[name].drop()
    bootstrap()
    admin = AuthService().ensure_bootstrap_admin()
    settings = get_settings()
    print("All collections dropped and recreated.")
    print(f"Admin ready: {admin.get('username')} / {settings.admin_password}")


if __name__ == "__main__":
    main()
