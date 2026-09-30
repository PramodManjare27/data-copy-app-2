"""
Creates the auth_users table (if needed) and seeds demo accounts.

Both app instances (prod_preprod, preprod_dev) point at the same auth/audit
database by default (see app/config.py DATABASE_URL) - AuditLog.app_mode is
what distinguishes which console a given audit row came from. Run this once
before starting either app for the first time:

    python scripts/seed_db.py

CHANGE THESE PASSWORDS before using this anywhere but local/demo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import User

DEMO_USERS = [
    {"username": "admin", "email": "admin@example.com", "password": "Admin@12345", "role": "admin"},
    {"username": "alice", "email": "alice@example.com", "password": "Alice@12345", "role": "user"},
    {"username": "bob", "email": "bob@example.com", "password": "Bob@123456", "role": "user"},
]


def main():
    app = create_app("prod_preprod")
    with app.app_context():
        db.create_all()
        for u in DEMO_USERS:
            existing = User.query.filter_by(username=u["username"]).first()
            if existing:
                print(f"user '{u['username']}' already exists — skipping")
                continue
            user = User(username=u["username"], email=u["email"], role=u["role"])
            user.set_password(u["password"])
            db.session.add(user)
            print(f"created user '{u['username']}' (role={u['role']})")
        db.session.commit()
    print("\nDemo credentials (CHANGE IN ANY NON-LOCAL ENVIRONMENT):")
    for u in DEMO_USERS:
        print(f"  {u['username']} / {u['password']}  [{u['role']}]")


if __name__ == "__main__":
    main()
