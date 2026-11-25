"""Runtime configuration for the FABRIX backend.

Values can be overridden with environment variables so the same code works
locally with SQLite and later with MySQL/PostgreSQL in production.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "fabrix.db"

DATABASE_URL = os.getenv("FABRIX_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")
SECRET_KEY = os.getenv("FABRIX_SECRET_KEY", "fabrix-local-development-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("FABRIX_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
API_PREFIX = "/api/v1"

# URLs used by the browser client. Keep localhost so demo pages are unchanged.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FABRIX_FRONTEND_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
