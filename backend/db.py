"""Database engine, session factory, and dependency injection."""
from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs = (
    {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if _is_sqlite
    else {}
)

engine = create_engine(DATABASE_URL, echo=False, future=True, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_integrity(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class Base(DeclarativeBase):
    """Shared declarative base for all FABRIX ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields one scoped database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not exist yet.

    Models are imported here so SQLAlchemy sees them before create_all(), while
    avoiding circular imports at module load time.
    """
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_schema_migrations()


def _run_schema_migrations() -> None:
    """Apply idempotent local schema/data migrations.

    The original prototype had no migration tool. This dependency-free runner
    provides a safe bridge for the existing SQLite database; future production
    deployments should move these statements into a versioned migration tool.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version VARCHAR(64) PRIMARY KEY, applied_at DATETIME NOT NULL)"
            )
        )
        applied = {
            row[0]
            for row in connection.execute(text("SELECT version FROM schema_migrations"))
        }
        inspector = inspect(connection)
        if "payments" in inspector.get_table_names():
            payment_columns = {
                column["name"] for column in inspector.get_columns("payments")
            }
            if "user_id" not in payment_columns:
                connection.execute(text("ALTER TABLE payments ADD COLUMN user_id INTEGER"))
            if "request_hash" not in payment_columns:
                connection.execute(
                    text("ALTER TABLE payments ADD COLUMN request_hash VARCHAR(128)")
                )
            if "operation" not in payment_columns:
                connection.execute(
                    text(
                        "ALTER TABLE payments ADD COLUMN operation VARCHAR(40) "
                        "NOT NULL DEFAULT 'checkout'"
                    )
                )
            connection.execute(
                text(
                    "UPDATE payments SET user_id = ("
                    "SELECT user_id FROM orders WHERE orders.id = payments.order_id"
                    ") WHERE user_id IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE payments SET request_hash = 'legacy:' || idempotency_key "
                    "WHERE request_hash IS NULL"
                )
            )
            connection.execute(text("DROP INDEX IF EXISTS ix_payments_idempotency_key"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_payments_idempotency_key "
                    "ON payments (idempotency_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_payment_user_operation_key "
                    "ON payments (user_id, operation, idempotency_key)"
                )
            )
        if "seller_orders" in inspector.get_table_names():
            connection.execute(
                text(
                    "UPDATE seller_orders SET seller_user_id = ("
                    "SELECT p.artisan_id FROM order_items oi "
                    "JOIN products p ON p.id = oi.product_id "
                    "WHERE oi.seller_order_id = seller_orders.id "
                    "AND p.artisan_id IS NOT NULL LIMIT 1"
                    ") WHERE seller_user_id IS NULL"
                )
            )
        if "recommendation_events" in inspector.get_table_names():
            event_columns = {
                column["name"]
                for column in inspector.get_columns("recommendation_events")
            }
            additions = {
                "occurred_at": "DATETIME",
                "received_at": "DATETIME",
                "session_id": "VARCHAR(120)",
                "source_context": "VARCHAR(120)",
                "recommendation_request_id": "VARCHAR(120)",
                "model_version": "VARCHAR(80)",
                "position": "INTEGER",
                "consent_snapshot": "BOOLEAN NOT NULL DEFAULT 0",
            }
            for name, ddl in additions.items():
                if name not in event_columns:
                    connection.execute(
                        text(f"ALTER TABLE recommendation_events ADD COLUMN {name} {ddl}")
                    )
            connection.execute(
                text(
                    "UPDATE recommendation_events SET "
                    "occurred_at = COALESCE(occurred_at, created_at), "
                    "received_at = COALESCE(received_at, created_at) "
                    "WHERE occurred_at IS NULL OR received_at IS NULL"
                )
            )
        integrity_triggers = {
            "trg_products_nonnegative_insert": """
                CREATE TRIGGER IF NOT EXISTS trg_products_nonnegative_insert
                BEFORE INSERT ON products
                WHEN NEW.price < 0 OR NEW.stock < 0 OR NEW.reserved_stock < 0
                    OR NEW.reserved_stock > NEW.stock
                BEGIN SELECT RAISE(ABORT, 'invalid product inventory or price'); END
            """,
            "trg_products_nonnegative_update": """
                CREATE TRIGGER IF NOT EXISTS trg_products_nonnegative_update
                BEFORE UPDATE OF price, stock, reserved_stock ON products
                WHEN NEW.price < 0 OR NEW.stock < 0 OR NEW.reserved_stock < 0
                    OR NEW.reserved_stock > NEW.stock
                BEGIN SELECT RAISE(ABORT, 'invalid product inventory or price'); END
            """,
            "trg_cart_quantity_insert": """
                CREATE TRIGGER IF NOT EXISTS trg_cart_quantity_insert
                BEFORE INSERT ON cart_items
                WHEN NEW.quantity < 1 OR NEW.quantity > 99
                BEGIN SELECT RAISE(ABORT, 'invalid cart quantity'); END
            """,
            "trg_cart_quantity_update": """
                CREATE TRIGGER IF NOT EXISTS trg_cart_quantity_update
                BEFORE UPDATE OF quantity ON cart_items
                WHEN NEW.quantity < 1 OR NEW.quantity > 99
                BEGIN SELECT RAISE(ABORT, 'invalid cart quantity'); END
            """,
            "trg_orders_amounts": """
                CREATE TRIGGER IF NOT EXISTS trg_orders_amounts
                BEFORE INSERT ON orders
                WHEN NEW.subtotal < 0 OR NEW.shipping < 0 OR NEW.tax < 0 OR NEW.total < 0
                BEGIN SELECT RAISE(ABORT, 'invalid order amount'); END
            """,
            "trg_orders_amounts_update": """
                CREATE TRIGGER IF NOT EXISTS trg_orders_amounts_update
                BEFORE UPDATE OF subtotal, shipping, tax, total ON orders
                WHEN NEW.subtotal < 0 OR NEW.shipping < 0 OR NEW.tax < 0 OR NEW.total < 0
                BEGIN SELECT RAISE(ABORT, 'invalid order amount'); END
            """,
            "trg_payments_amounts": """
                CREATE TRIGGER IF NOT EXISTS trg_payments_amounts
                BEFORE INSERT ON payments
                WHEN NEW.amount < 0
                BEGIN SELECT RAISE(ABORT, 'invalid payment amount'); END
            """,
            "trg_payments_amounts_update": """
                CREATE TRIGGER IF NOT EXISTS trg_payments_amounts_update
                BEFORE UPDATE OF amount ON payments
                WHEN NEW.amount < 0
                BEGIN SELECT RAISE(ABORT, 'invalid payment amount'); END
            """,
            "trg_reviews_rating": """
                CREATE TRIGGER IF NOT EXISTS trg_reviews_rating
                BEFORE INSERT ON reviews
                WHEN NEW.rating < 1 OR NEW.rating > 5
                BEGIN SELECT RAISE(ABORT, 'invalid review rating'); END
            """,
            "trg_reviews_rating_update": """
                CREATE TRIGGER IF NOT EXISTS trg_reviews_rating_update
                BEFORE UPDATE OF rating ON reviews
                WHEN NEW.rating < 1 OR NEW.rating > 5
                BEGIN SELECT RAISE(ABORT, 'invalid review rating'); END
            """,
        }
        for ddl in integrity_triggers.values():
            connection.execute(text(ddl))
        money_columns = {
            "products": {"price": "price_cents", "compare_at_price": "compare_at_price_cents"},
            "orders": {
                "subtotal": "subtotal_cents", "shipping": "shipping_cents",
                "tax": "tax_cents", "total": "total_cents",
            },
            "seller_orders": {
                "subtotal": "subtotal_cents", "shipping": "shipping_cents",
                "total": "total_cents",
            },
            "order_items": {"unit_price": "unit_price_cents", "line_total": "line_total_cents"},
            "payments": {"amount": "amount_cents"},
        }
        for table, fields in money_columns.items():
            if table not in inspector.get_table_names():
                continue
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            for old_name, cents_name in fields.items():
                if cents_name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {cents_name} INTEGER")
                    )
                rows = connection.execute(
                    text(
                        f"SELECT rowid, {old_name}, {cents_name} "
                        f"FROM {table} WHERE {cents_name} IS NULL "
                        f"OR ({cents_name} = 0 AND {old_name} != 0)"
                    )
                ).all()
                for rowid, old_value, _ in rows:
                    if old_value is None:
                        connection.execute(
                            text(
                                f"UPDATE {table} SET {cents_name} = NULL WHERE rowid = :rowid"
                            ),
                            {"rowid": rowid},
                        )
                        continue
                    decimal_value = Decimal(str(old_value))
                    cents = decimal_value * 100
                    if cents != cents.to_integral_value():
                        raise RuntimeError(
                            f"Monetary precision exceeds cents in {table}.{old_name}: {old_value}"
                        )
                    connection.execute(
                        text(
                            f"UPDATE {table} SET {cents_name} = :cents WHERE rowid = :rowid"
                        ),
                        {"cents": int(cents), "rowid": rowid},
                    )
        migrations = [
            ("payments_idempotency_v1", "Payment idempotency is user-scoped"),
            ("sqlite_foreign_keys_v1", "SQLite foreign keys enabled"),
            ("recommendation_event_context_v1", "Recommendation event provenance fields"),
            ("integrity_triggers_v1", "SQLite integrity triggers for legacy tables"),
            ("money_minor_units_v1", "Integer minor-unit monetary columns"),
        ]
        for version, _description in migrations:
            if version not in applied:
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations(version, applied_at) "
                        "VALUES (:version, CURRENT_TIMESTAMP)"
                    ),
                    {"version": version},
                )
