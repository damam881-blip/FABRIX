"""Print a readable report of the local FABRIX SQLite database.

Examples:
    python scripts/inspect_db.py
    python scripts/inspect_db.py --table orders
    python scripts/inspect_db.py --full
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "fabrix.db"

KEY_TABLES = {
    "users": ("id", "email", "full_name", "role", "can_sell", "studio_name"),
    "stores": ("id", "user_id", "name", "state", "craft"),
    "products": ("id", "name", "artisan", "category", "price", "stock", "status"),
    "orders": ("id", "order_number", "status", "customer_email", "total", "placed_at"),
    "seller_orders": ("id", "seller_order_number", "seller_name", "status", "total"),
    "reviews": ("id", "product_id", "order_item_id", "rating", "status"),
    "audit_logs": ("id", "actor_id", "action", "target_type", "target_id"),
    "reservations": ("id", "product_id", "quantity", "status", "expires_at"),
}
HIDDEN_COLUMNS = {"password_hash"}


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({quoted(table)})")]


def short(value: object, limit: int = 120) -> str:
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_rows(conn: sqlite3.Connection, table: str, fields: tuple[str, ...] | list[str]) -> None:
    available = columns(conn, table)
    use = [field for field in fields if field in available and field not in HIDDEN_COLUMNS]
    if not use:
        use = [field for field in available if field not in HIDDEN_COLUMNS]
    selected = ", ".join(quoted(field) for field in use)
    rows = conn.execute(f"SELECT {selected} FROM {quoted(table)} ORDER BY id").fetchall()
    print(f"\n[{table}] {len(rows)} row(s)")
    if not rows:
        return
    for row in rows:
        print("  " + " | ".join(f"{field}={short(row[field])}" for field in use))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file to inspect")
    parser.add_argument("--table", help="print every row from one table")
    parser.add_argument("--full", action="store_true", help="print every row from every table")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"No database found at {args.db}. Run: python -m backend.seed")
        return

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]
    print(f"Database: {args.db} ({args.db.stat().st_size:,} bytes)")
    print(f"Tables: {len(tables)}")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {quoted(table)}").fetchone()[0]
        print(f"  {table:<26} {count:>5}")

    if args.table:
        if args.table not in tables:
            raise SystemExit(f"Unknown table: {args.table}")
        print_rows(conn, args.table, columns(conn, args.table))
    elif args.full:
        for table in tables:
            print_rows(conn, table, columns(conn, table))
    else:
        for table in KEY_TABLES:
            if table in tables:
                print_rows(conn, table, KEY_TABLES[table])
        print("\nUse --table <name> or --full for more detail.")


if __name__ == "__main__":
    main()
