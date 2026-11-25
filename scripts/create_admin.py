"""Provision a FABRIX administrator without exposing admin registration over HTTP.

The operator must set FABRIX_ADMIN_BOOTSTRAP_SECRET in the environment and
enter that secret interactively. Passwords are never accepted as CLI
arguments, so they do not appear in shell history or process listings.

Example:
    $env:FABRIX_ADMIN_BOOTSTRAP_SECRET = "operator-only-secret"
    python scripts/create_admin.py --email admin2@example.com --name "FABRIX Admin"
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from backend.db import SessionLocal, init_db
from backend.models import AuditLog, User
from backend.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    configured_secret = os.getenv("FABRIX_ADMIN_BOOTSTRAP_SECRET")
    if not configured_secret:
        print("FABRIX_ADMIN_BOOTSTRAP_SECRET must be configured.", file=sys.stderr)
        return 2
    entered_secret = getpass.getpass("Bootstrap secret: ")
    if entered_secret != configured_secret:
        print("Bootstrap secret rejected.", file=sys.stderr)
        return 1

    password = getpass.getpass("New admin password: ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if len(password) < 12 or password != confirmation:
        print("Passwords must match and be at least 12 characters.", file=sys.stderr)
        return 2

    init_db()
    db = SessionLocal()
    try:
        email = args.email.strip().lower()
        if db.scalar(select(User).where(User.email == email)):
            print("An account with that email already exists.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=args.name.strip(),
            role="admin",
            can_shop=True,
            can_sell=False,
            consent=False,
            personalization=False,
        )
        db.add(user)
        db.commit()
        db.add(
            AuditLog(
                action="admin.provisioned",
                target_type="user",
                target_id=str(user.id),
                reason="Out-of-band bootstrap",
                extra={"email": email},
            )
        )
        db.commit()
        print("Administrator provisioned.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
