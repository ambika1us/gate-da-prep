from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings
from database import bootstrap
from services.auth_service import AuthService


def main() -> None:
    info = bootstrap()
    admin = AuthService().ensure_bootstrap_admin()
    settings = get_settings()
    print(f"Database: {info['db_name']} (fallback={info['fallback']})")
    print("Indexes created.")
    print("Default admin:")
    print(f"  Username: {admin.get('username')}")
    print(f"  Email: {admin.get('email')}")
    print(f"  Password: {settings.admin_password}")


if __name__ == "__main__":
    main()
