#!/usr/bin/env python3
"""One-command launcher for FABRIX frontend + backend.

Ensures local photos/CSS exist, then starts:
  * FastAPI backend at http://127.0.0.1:8000/ (also serves the static pages)
  * Legacy static server at http://127.0.0.1:5500/ for existing browser tests

Run: python start.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

API_PORT = int(os.getenv("FABRIX_API_PORT", "8000"))
STATIC_PORT = int(os.getenv("FABRIX_STATIC_PORT", "5500"))


def missing_photos() -> bool:
    products = ROOT / "assets/photos/products"
    needed = [products / f"product-{i:02d}.jpg" for i in range(1, 13)]
    editorial_registry = json.loads(
        (ROOT / "assets/photos/editorial-sources.json").read_text(encoding="utf-8")
    )
    editorial = [
        ROOT / "assets/photos" / row["folder"] / f"{row['name']}.jpg"
        for row in editorial_registry
    ]
    return (
        any(not path.exists() for path in needed + editorial)
        or not (ROOT / "css/local-photos.css").exists()
        or not (ROOT / "css/editorial-photos.css").exists()
    )


def ensure_photos() -> None:
    if not missing_photos():
        return
    print("Local photos missing; downloading now (requires internet once)...")
    subprocess.run([sys.executable, "scripts/download_photos.py"], check=False)
    subprocess.run([sys.executable, "scripts/download_editorial_photos.py"], check=False)


def ensure_dependencies() -> None:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        import sqlalchemy  # noqa: F401
        import jose  # noqa: F401
        import bcrypt  # noqa: F401
    except ImportError:
        print("Installing backend dependencies from requirements.txt...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )


def launch() -> None:
    ensure_photos()
    ensure_dependencies()

    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(API_PORT),
            ]
        )
    ]
    if STATIC_PORT:
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", "http.server", str(STATIC_PORT)]
            )
        )

    print(f"FABRIX API + site: http://127.0.0.1:{API_PORT}/")
    print(f"Legacy static site: http://127.0.0.1:{STATIC_PORT}/")
    print(f"API docs: http://127.0.0.1:{API_PORT}/docs")
    print("Press Ctrl+C to stop.")

    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping FABRIX servers...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    launch()
