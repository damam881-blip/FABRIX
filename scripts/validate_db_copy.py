"""Validate a copied FABRIX SQLite database without changing the source."""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"source database does not exist: {args.source}")
    if args.destination.exists():
        parser.error(f"destination already exists: {args.destination}")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, args.destination)

    os.environ["FABRIX_DATABASE_URL"] = f"sqlite:///{args.destination.resolve().as_posix()}"
    from backend.db import engine, init_db

    init_db()
    with engine.connect() as connection:
        integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        migrations = connection.exec_driver_sql(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    if integrity != "ok" or foreign_keys or enabled != 1:
        print(
            f"FAILED integrity={integrity!r} foreign_key_check={foreign_keys!r} "
            f"foreign_keys={enabled!r}"
        )
        return 1
    print(f"validated={args.destination}")
    print("integrity_check=ok")
    print("foreign_key_check=ok")
    print("foreign_keys=1")
    print(f"migrations={[row[0] for row in migrations]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
