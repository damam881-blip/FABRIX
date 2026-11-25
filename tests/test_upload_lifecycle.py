"""Dedicated local-MVP regression coverage for the managed upload lifecycle."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DB_PATH = Path(tempfile.gettempdir()) / "fabrix_test_api.db"
os.environ.setdefault("FABRIX_DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
os.environ.setdefault("FABRIX_SECRET_KEY", "test-secret-key")
os.environ.setdefault("FABRIX_SEED_DEMO_USERS", "1")

from backend.db import SessionLocal  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import AuditLog, Product, UploadAsset  # noqa: E402
from backend.routers import products as products_router  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"upload-lifecycle-test"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def upload_env(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "uploads" / "products"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(products_router, "UPLOAD_DIR", root)

    db = SessionLocal()
    try:
        products = {
            row.id: (row.image, list(row.images or []), row.status)
            for row in db.scalars(select(Product)).all()
        }
        max_asset_id = db.scalar(select(func.max(UploadAsset.id))) or 0
        max_audit_id = db.scalar(select(func.max(AuditLog.id))) or 0
    finally:
        db.close()

    yield SimpleNamespace(
        client=client, root=root, tmp_path=tmp_path, max_asset_id=max_asset_id
    )

    db = SessionLocal()
    try:
        for row in db.scalars(select(Product)).all():
            if row.id in products:
                image, images, status = products[row.id]
                row.image = image
                row.images = list(images)
                row.status = status
        db.query(UploadAsset).filter(UploadAsset.id > max_asset_id).delete(
            synchronize_session=False
        )
        db.query(AuditLog).filter(AuditLog.id > max_audit_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def token_for(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def artisan_token(client: TestClient) -> str:
    return token_for(client, "artisan@example.com", "Demo12345")


def admin_token(client: TestClient) -> str:
    return token_for(client, "admin@example.com", "Admin12345")


def product_snapshot(product_id: int) -> tuple[Any, tuple[str, ...], str]:
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        assert product is not None
        return product.image, tuple(product.images or []), product.status
    finally:
        db.close()


def set_product_images(product_id: int, images: list[str], image: str | None) -> None:
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        assert product is not None
        product.images = list(images)
        product.image = image
        db.commit()
    finally:
        db.close()


def write_file(env, product_id: int, filename: str, content: bytes = PNG) -> Path:
    path = env.root / str(product_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def upload_url(product_id: int, filename: str) -> str:
    return f"/assets/uploads/products/{product_id}/{filename}"


def add_asset(
    product_id: int, path: Path, *, missing: bool = False
) -> int:
    size = 0 if missing else path.stat().st_size
    digest = "0" * 64 if missing else hashlib.sha256(path.read_bytes()).hexdigest()
    db = SessionLocal()
    try:
        asset = UploadAsset(
            product_id=product_id,
            path=str(path.resolve()),
            content_type="image/png",
            size_bytes=size,
            sha256=digest,
        )
        db.add(asset)
        db.commit()
        return int(asset.id)
    finally:
        db.close()


def asset_ids() -> set[int]:
    db = SessionLocal()
    try:
        return {row.id for row in db.scalars(select(UploadAsset)).all()}
    finally:
        db.close()


def asset_paths() -> set[Path]:
    db = SessionLocal()
    try:
        return {
            Path(row.path).resolve()
            for row in db.scalars(select(UploadAsset)).all()
        }
    finally:
        db.close()


def upload_image(
    client: TestClient,
    token: str,
    product_id: int,
    filename: str,
    content: bytes = PNG,
    *,
    replace: bool = False,
):
    suffix = "?replace=true" if replace else ""
    return client.post(
        f"/api/v1/products/{product_id}/images{suffix}",
        headers=auth(token),
        files={"file": (filename, content, "image/png")},
    )


def cleanup(
    client: TestClient, token: str, *, dry_run: bool = True
):
    return client.post(
        f"/api/v1/admin/uploads/cleanup?dry_run={'true' if dry_run else 'false'}",
        headers=auth(token),
    )


def latest_audit_id() -> int:
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.max(AuditLog.id))) or 0)
    finally:
        db.close()


def audit_count_since(
    action: str, min_id: int, target_id: str | None = None
) -> int:
    db = SessionLocal()
    try:
        query = select(func.count(AuditLog.id)).where(
            AuditLog.action == action, AuditLog.id > min_id
        )
        if target_id is not None:
            query = query.where(AuditLog.target_id == target_id)
        return int(db.scalar(query) or 0)
    finally:
        db.close()


def uploaded_url_from(payload: dict[str, Any], product_id: int) -> str:
    marker = f"/assets/uploads/products/{product_id}/"
    matches = [url for url in payload["images"] if marker in url]
    assert matches, payload
    return matches[-1]


def test_successful_replacement_removes_obsolete_managed_file(upload_env):
    token = artisan_token(upload_env.client)
    first = upload_image(upload_env.client, token, 3, "first.png")
    assert first.status_code == 200, first.text
    old_url = uploaded_url_from(first.json(), 3)
    old_path = upload_env.root / "3" / Path(old_url).name

    second = upload_image(
        upload_env.client, token, 3, "second.png", replace=True
    )
    assert second.status_code == 200, second.text
    new_url = uploaded_url_from(second.json(), 3)
    assert new_url != old_url
    assert not old_path.exists()
    assert Path(old_path).resolve() not in asset_paths()
    assert tuple(second.json()["images"]) == (new_url,)


def test_invalid_image_rejected_without_product_mutation(upload_env):
    token = artisan_token(upload_env.client)
    before = product_snapshot(3)
    before_assets = asset_ids()
    response = upload_image(
        upload_env.client, token, 3, "fake.png", b"not-an-image"
    )
    assert response.status_code == 400
    assert product_snapshot(3) == before
    assert asset_ids() == before_assets


def test_commit_failure_during_replacement_rolls_back_and_cleans_new_file(
    upload_env, monkeypatch: pytest.MonkeyPatch
):
    token = artisan_token(upload_env.client)
    before = product_snapshot(3)
    before_files = {path.resolve() for path in upload_env.root.rglob("*") if path.is_file()}
    before_assets = asset_ids()

    original_commit = Session.commit
    state = {"calls": 0}

    def failing_commit(session: Session):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("simulated commit failure")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = upload_image(upload_env.client, token, 3, "rollback.png")
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert state["calls"] == 1
    assert product_snapshot(3) == before
    assert asset_ids() == before_assets
    after_files = {path.resolve() for path in upload_env.root.rglob("*") if path.is_file()}
    assert after_files == before_files


def test_shared_image_referenced_by_another_product_is_protected(upload_env):
    token = artisan_token(upload_env.client)
    first = upload_image(upload_env.client, token, 3, "shared.png")
    assert first.status_code == 200, first.text
    old_url = uploaded_url_from(first.json(), 3)
    old_path = upload_env.root / "3" / Path(old_url).name
    set_product_images(4, [old_url], old_url)

    second = upload_image(
        upload_env.client, token, 3, "replacement.png", replace=True
    )
    assert second.status_code == 200, second.text
    assert old_path.exists()
    assert product_snapshot(4)[1] == (old_url,)
    assert Path(old_path).resolve() in asset_paths()
    assert product_snapshot(3)[1] == (uploaded_url_from(second.json(), 3),)


def test_shared_image_referenced_by_another_image_entry_is_protected(upload_env):
    token = artisan_token(upload_env.client)
    first = upload_image(upload_env.client, token, 3, "duplicate.png")
    assert first.status_code == 200, first.text
    old_url = uploaded_url_from(first.json(), 3)
    old_path = upload_env.root / "3" / Path(old_url).name
    set_product_images(4, [old_url, old_url], old_url)

    second = upload_image(
        upload_env.client, token, 3, "duplicate-replacement.png", replace=True
    )
    assert second.status_code == 200, second.text
    assert old_path.exists()
    assert product_snapshot(4)[1] == (old_url, old_url)
    assert Path(old_path).resolve() in asset_paths()


def test_legacy_product_image_without_metadata_is_preserved(upload_env):
    legacy = write_file(upload_env, 3, "legacy.png")
    url = upload_url(3, "legacy.png")
    set_product_images(3, [url], url)

    response = cleanup(upload_env.client, admin_token(upload_env.client), dry_run=False)
    assert response.status_code == 200, response.text
    data = response.json()
    assert legacy.exists()
    assert data["candidate_count"] == 0
    protected = [item["relative_path"] for item in data["protected"]]
    assert "3/legacy.png" in protected
    assert not any(item["relative_path"] == "3/legacy.png" for item in data["candidates"])


def test_unreferenced_generated_file_is_classified_correctly(upload_env):
    orphan = write_file(upload_env, 3, "generated.png")
    response = cleanup(upload_env.client, admin_token(upload_env.client))
    assert response.status_code == 200, response.text
    data = response.json()
    matching = [
        item for item in data["candidates"] if item["relative_path"] == "3/generated.png"
    ]
    assert len(matching) == 1
    assert matching[0]["kind"] == "legacy"
    assert matching[0]["reason"] == "unreferenced_generated_file"
    assert matching[0]["path"] == str(orphan.resolve())
    assert orphan.exists()


def test_valid_managed_upload_is_not_classified_as_orphan(upload_env):
    token = artisan_token(upload_env.client)
    response = upload_image(upload_env.client, token, 3, "valid.png")
    assert response.status_code == 200, response.text
    url = uploaded_url_from(response.json(), 3)
    path = upload_env.root / "3" / Path(url).name

    report = cleanup(upload_env.client, admin_token(upload_env.client))
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["candidate_count"] == 0
    protected = [item["relative_path"] for item in data["protected"]]
    assert "3/" + path.name in protected


def test_true_managed_orphan_detection(upload_env):
    token = artisan_token(upload_env.client)
    response = upload_image(upload_env.client, token, 3, "managed-orphan.png")
    assert response.status_code == 200, response.text
    url = uploaded_url_from(response.json(), 3)
    path = upload_env.root / "3" / Path(url).name
    set_product_images(3, [], None)

    dry = cleanup(upload_env.client, admin_token(upload_env.client))
    assert dry.status_code == 200, dry.text
    candidates = [
        item for item in dry.json()["candidates"] if item["relative_path"] == "3/" + path.name
    ]
    assert len(candidates) == 1
    assert candidates[0]["kind"] == "managed"

    result = cleanup(
        upload_env.client, admin_token(upload_env.client), dry_run=False
    )
    assert result.status_code == 200, result.text
    assert not path.exists()
    assert Path(path).resolve() not in asset_paths()


def test_dry_run_reports_candidates_without_deleting_or_mutating(upload_env):
    orphan = write_file(upload_env, 3, "dry-run.png")
    missing_path = upload_env.root / "3" / "stale-metadata.png"
    stale_id = add_asset(3, missing_path, missing=True)
    before = product_snapshot(3)

    first = cleanup(upload_env.client, admin_token(upload_env.client))
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["dry_run"] is True
    assert data["deleted_count"] == 0
    assert data["failed_count"] == 0
    assert data["candidate_count"] == 1
    assert data["candidates"][0]["relative_path"] == "3/dry-run.png"
    assert data["stale_metadata_count"] == 1
    assert any(item["relative_path"] == "3/stale-metadata.png" for item in data["stale_metadata"])

    second = cleanup(upload_env.client, admin_token(upload_env.client))
    assert second.json() == data
    assert orphan.exists()
    assert stale_id in asset_ids()
    assert product_snapshot(3) == before


def test_non_dry_cleanup_deletes_only_confirmed_safe_candidates(upload_env):
    protected = write_file(upload_env, 3, "protected.png")
    protected_url = upload_url(3, "protected.png")
    set_product_images(3, [protected_url], protected_url)
    legacy_orphan = write_file(upload_env, 3, "legacy-orphan.png")
    managed_orphan = write_file(upload_env, 3, "managed-orphan.png")
    add_asset(3, managed_orphan)

    response = cleanup(
        upload_env.client, admin_token(upload_env.client), dry_run=False
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["deleted_count"] == 2
    assert not legacy_orphan.exists()
    assert not managed_orphan.exists()
    assert protected.exists()
    assert Path(managed_orphan).resolve() not in asset_paths()
    assert product_snapshot(3) == (protected_url, (protected_url,), "Published")


def test_failed_file_deletion_retains_retry_capability(
    upload_env, monkeypatch: pytest.MonkeyPatch
):
    orphan = write_file(upload_env, 3, "retry-needed.png")
    add_asset(3, orphan)
    baseline = latest_audit_id()
    original_unlink = Path.unlink

    def failing_unlink(path: Path, *args, **kwargs):
        if path.name == "retry-needed.png":
            raise OSError("simulated unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    response = cleanup(
        upload_env.client, admin_token(upload_env.client), dry_run=False
    )
    monkeypatch.setattr(Path, "unlink", original_unlink)

    assert response.status_code == 200, response.text
    data = response.json()
    assert str(orphan.resolve()) in data["failed"]
    assert data["deleted_count"] == 0
    assert orphan.exists()
    assert Path(orphan).resolve() in asset_paths()
    assert (
        audit_count_since(
            "upload.cleanup_failed", baseline, "3/retry-needed.png"
        )
        == 1
    )


def test_retry_after_failed_deletion_succeeds(
    upload_env, monkeypatch: pytest.MonkeyPatch
):
    orphan = write_file(upload_env, 3, "retry-ok.png")
    add_asset(3, orphan)
    baseline = latest_audit_id()
    original_unlink = Path.unlink

    def failing_unlink(path: Path, *args, **kwargs):
        if path.name == "retry-ok.png":
            raise OSError("simulated unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    failed = cleanup(
        upload_env.client, admin_token(upload_env.client), dry_run=False
    )
    monkeypatch.setattr(Path, "unlink", original_unlink)
    assert failed.json()["failed"] == [str(orphan.resolve())]

    retried = cleanup(
        upload_env.client, admin_token(upload_env.client), dry_run=False
    )
    assert retried.status_code == 200, retried.text
    data = retried.json()
    assert data["deleted_count"] == 1
    assert data["failed_count"] == 0
    assert not orphan.exists()
    assert Path(orphan).resolve() not in asset_paths()
    assert (
        audit_count_since("upload.cleanup_failed", baseline, "3/retry-ok.png")
        == 1
    )
    assert audit_count_since("upload.orphan_cleanup", baseline) == 1


def test_missing_file_with_valid_product_reference_is_reported_broken(upload_env):
    missing = upload_env.root / "3" / "missing.png"
    url = upload_url(3, "missing.png")
    set_product_images(3, [url], url)
    stale_id = add_asset(3, missing, missing=True)

    report = cleanup(upload_env.client, admin_token(upload_env.client))
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["broken_reference_count"] == 1
    assert any("3/missing.png" in item for item in data["broken_references"])
    assert data["candidate_count"] == 0
    assert data["stale_metadata_count"] == 0
    assert stale_id in asset_ids()
    assert not missing.exists()


def test_path_traversal_and_outside_root_references_are_ignored(upload_env):
    outside = upload_env.tmp_path / "outside.png"
    outside.write_bytes(PNG)
    traversal_url = "/assets/uploads/products/3/../../outside.png"
    set_product_images(3, [traversal_url], traversal_url)
    outside_asset_id = add_asset(3, outside)

    report = cleanup(upload_env.client, admin_token(upload_env.client))
    assert report.status_code == 200, report.text
    data = report.json()
    assert outside.exists()
    assert data["candidate_count"] == 0
    assert any("outside.png" in item for item in data["outside_root"])
    assert outside_asset_id in asset_ids()


def test_soft_unpublish_keeps_product_images(upload_env):
    image = write_file(upload_env, 3, "unpublished.png")
    url = upload_url(3, "unpublished.png")
    set_product_images(3, [url], url)
    token = artisan_token(upload_env.client)

    response = upload_env.client.delete(
        "/api/v1/products/3", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    assert product_snapshot(3) == (url, (url,), "Unpublished")
    assert image.exists()


def test_cleanup_is_idempotent(upload_env):
    orphan = write_file(upload_env, 3, "idempotent.png")
    admin = admin_token(upload_env.client)
    baseline = latest_audit_id()

    first = cleanup(upload_env.client, admin, dry_run=False)
    assert first.status_code == 200, first.text
    assert first.json()["deleted_count"] == 1
    assert audit_count_since("upload.orphan_cleanup", baseline) == 1

    second = cleanup(upload_env.client, admin, dry_run=False)
    assert second.status_code == 200, second.text
    data = second.json()
    assert data["candidate_count"] == 0
    assert data["deleted_count"] == 0
    assert data["failed_count"] == 0
    assert not orphan.exists()
    assert audit_count_since("upload.orphan_cleanup", baseline) == 1
