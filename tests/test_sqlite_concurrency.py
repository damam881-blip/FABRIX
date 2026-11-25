"""File-backed SQLite concurrency regression tests for atomic primitives."""
from __future__ import annotations

import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def test_two_connections_cannot_oversell_last_unit():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "inventory.db"
        connection = _connect(path)
        connection.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, stock INTEGER NOT NULL)")
        connection.execute("INSERT INTO products(id, stock) VALUES (1, 1)")
        connection.close()

        def purchase() -> int:
            db = _connect(path)
            try:
                db.execute("BEGIN IMMEDIATE")
                result = db.execute(
                    "UPDATE products SET stock = stock - 1 WHERE id = 1 AND stock >= 1"
                )
                db.commit()
                return result.rowcount
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: purchase(), range(2)))
        assert sorted(results) == [0, 1]
        db = _connect(path)
        assert db.execute("SELECT stock FROM products WHERE id = 1").fetchone()[0] == 0
        db.close()


def test_file_backed_idempotency_unique_key_allows_one_effect():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "payments.db"
        connection = _connect(path)
        connection.execute(
            "CREATE TABLE payments (id INTEGER PRIMARY KEY, user_id INTEGER, "
            "operation TEXT, idempotency_key TEXT, "
            "UNIQUE(user_id, operation, idempotency_key))"
        )
        connection.close()

        def insert_payment() -> str:
            db = _connect(path)
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO payments(user_id, operation, idempotency_key) VALUES (1, 'checkout', 'same')"
                )
                db.commit()
                return "inserted"
            except sqlite3.IntegrityError:
                db.rollback()
                return "duplicate"
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: insert_payment(), range(2)))
        assert sorted(results) == ["duplicate", "inserted"]
        db = _connect(path)
        assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
        db.close()
