"""Small shared helpers for the backend."""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "item"


def utcnow() -> datetime:
    """Naive UTC timestamp for database columns (SQLite drops tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def order_number() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"FX-{stamp}-{secrets.token_hex(3).upper()}"


MONEY_QUANTUM = Decimal("0.01")


def money_decimal(value: object) -> Decimal:
    """Convert through text to avoid carrying binary float artifacts."""
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def money_to_cents(value: object) -> int:
    exact = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return int(exact * 100)


def cents_to_money(cents: int) -> float:
    return float((Decimal(int(cents)) / 100).quantize(MONEY_QUANTUM))


def add_money(*values: object) -> float:
    total = sum((money_decimal(value) for value in values), Decimal("0"))
    return float(total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def multiply_money(value: object, quantity: int) -> float:
    return float((money_decimal(value) * quantity).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    ))


def round_money(value: object) -> float:
    return float(money_decimal(value))
