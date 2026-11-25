"""Cross-cutting backend services used by multiple routers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import secrets
from pathlib import Path
import hashlib
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from .config import ROOT
from .models import (
    AuditLog,
    Notification,
    Product,
    RecommendationDatasetSnapshot,
    RecommendationEvent,
    Reservation,
    Review,
    Store,
    UploadAsset,
    User,
)
from .utils import utcnow


def notify(db: Session, user_id: int, message: str) -> Notification:
    row = Notification(user_id=user_id, message=message)
    db.add(row)
    return row


def audit(
    db: Session,
    action: str,
    actor_id: int | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        reason=reason,
        extra=metadata or {},
    )
    db.add(row)
    return row


def recompute_product_rating(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    if not product:
        return
    approved = db.scalars(
        select(Review).where(Review.product_id == product_id, Review.status == "approved")
    ).all()
    product.reviews_count = len(approved)
    product.rating = round(sum(r.rating for r in approved) / len(approved), 2) if approved else 4.8


def product_is_eligible(db: Session, product: Product) -> bool:
    """Central purchase/recommendation eligibility predicate."""
    if product.status != "Published" or product.available_stock <= 0:
        return False
    if product.artisan_id is None:
        return False
    owner = db.get(User, product.artisan_id)
    store = db.scalar(select(Store).where(Store.user_id == product.artisan_id))
    return bool(
        owner
        and owner.is_active
        and owner.can_sell
        and store
        and store.state == "Approved"
    )


def purge_recommendation_events(
    db: Session, retention_days: int, actor_id: int | None = None
) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    rows = list(
        db.scalars(
            select(RecommendationEvent).where(RecommendationEvent.created_at < cutoff)
        ).all()
    )
    for row in rows:
        db.delete(row)
    if rows:
        audit(
            db,
            "recommendation.retention_cleanup",
            actor_id=actor_id,
            target_type="recommendation_events",
            target_id=cutoff.isoformat(),
            metadata={"deleted": len(rows), "retention_days": retention_days},
        )
    return len(rows)


def create_recommendation_snapshot(db: Session, actor_id: int | None = None) -> RecommendationDatasetSnapshot:
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.is_active.is_(True))).all()
    }
    events = list(db.scalars(select(RecommendationEvent)).all())
    eligible = [
        event for event in events
        if event.user_id is None
        or (event.user_id in users and users[event.user_id].consent and users[event.user_id].is_active)
    ]
    reasons = {
        "consent_or_inactive_user": len(events) - len(eligible),
        "retention": 0,
    }
    watermark = max((event.received_at for event in events), default=None)
    snapshot = RecommendationDatasetSnapshot(
        snapshot_id=f"snap_{secrets.token_urlsafe(12)}",
        watermark=watermark,
        taxonomy_version="v1",
        criteria={
            "consent_required_for_authenticated_events": True,
            "active_users_only": True,
            "retention_days": 90,
        },
        included_count=len(eligible),
        excluded_count=len(events) - len(eligible),
        exclusion_reasons=reasons,
    )
    db.add(snapshot)
    audit(
        db,
        "recommendation.snapshot.created",
        actor_id=actor_id,
        target_type="recommendation_snapshot",
        target_id=snapshot.snapshot_id,
        metadata={"included": len(eligible), "excluded": len(events) - len(eligible)},
    )
    return snapshot


@dataclass
class UploadCleanupItem:
    path: str
    relative_path: str
    kind: str
    reason: str


@dataclass
class UploadCleanupReport:
    dry_run: bool
    candidates: list[UploadCleanupItem] = field(default_factory=list)
    protected: list[UploadCleanupItem] = field(default_factory=list)
    broken_references: list[str] = field(default_factory=list)
    legacy_references: list[str] = field(default_factory=list)
    stale_metadata: list[UploadCleanupItem] = field(default_factory=list)
    unresolvable_references: list[str] = field(default_factory=list)
    outside_root: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _iter_reference_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_reference_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_reference_strings(item)


def _reference_strings(*values: Any) -> Iterator[str]:
    for value in values:
        yield from _iter_reference_strings(value)


def _reference_basename(reference: str) -> str:
    parsed = urlparse(reference)
    text = parsed.path if parsed.scheme in {"http", "https"} else reference
    return Path(text.replace("\\", "/")).name


def _reference_to_path(reference: Any, upload_root: Path) -> tuple[Path | None, str]:
    """Resolve a stored product image reference without leaving upload_root."""
    raw = str(reference).strip()
    if not raw:
        return None, "empty"
    parsed = urlparse(raw)
    is_http_url = parsed.scheme in {"http", "https"}
    slashed = raw.replace("\\", "/")
    url_style = (
        is_http_url
        or slashed.startswith("/assets/")
        or slashed.startswith("assets/")
    )
    if is_http_url:
        normalized = (parsed.path or "").replace("\\", "/")
    elif url_style:
        normalized = slashed
    else:
        normalized = raw

    root_resolved = upload_root.resolve(strict=False)
    if url_style and "/uploads/products/" not in normalized:
        # Legacy product photography lives under /assets/photos and is never
        # managed by this cleanup. Preserve it without flagging it as an
        # attempted escape from the managed upload root.
        try:
            legacy_root = (ROOT / "assets").resolve(strict=False)
        except (OSError, RuntimeError):
            return None, "unresolvable"
        candidate = ROOT / normalized.lstrip("/")
        try:
            candidate.resolve(strict=False).relative_to(legacy_root)
        except ValueError:
            return None, "outside_root"
        return None, "external_legacy"

    if not url_style and Path(raw).is_absolute():
        candidate = Path(raw)
    elif "/uploads/products/" in normalized:
        suffix = normalized.split("/uploads/products/", 1)[1].lstrip("/")
        candidate = upload_root / suffix
    elif normalized.startswith("/assets/") or normalized.startswith("assets/"):
        candidate = ROOT / normalized.lstrip("/")
    else:
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = ROOT / candidate

    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "unresolvable"
    if resolved == root_resolved:
        return None, "unmanaged"
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None, "outside_root"
    return resolved, "ok"


def _relative_upload_path(path: Path, upload_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            upload_root.resolve(strict=False)
        ).as_posix()
    except (OSError, RuntimeError, ValueError):
        return str(path)


def _cleanup_item(path: Path, upload_root: Path, kind: str, reason: str) -> UploadCleanupItem:
    return UploadCleanupItem(
        path=str(path),
        relative_path=_relative_upload_path(path, upload_root),
        kind=kind,
        reason=reason,
    )


def _product_reference_paths(
    db: Session, upload_root: Path
) -> tuple[dict[Path, set[int]], set[str], set[str], set[str], set[str]]:
    referenced: dict[Path, set[int]] = {}
    unresolvable: set[str] = set()
    outside: set[str] = set()
    legacy: set[str] = set()
    ambiguous_names: set[str] = set()
    for product in db.scalars(select(Product)).all():
        for reference in _reference_strings(
            product.images, product.image, product.details, product.materials
        ):
            path, status = _reference_to_path(reference, upload_root)
            if status == "ok" and path is not None:
                referenced.setdefault(path, set()).add(product.id)
            elif status == "external_legacy":
                legacy.add(str(reference))
            elif status in {"unresolvable", "outside_root"}:
                (unresolvable if status == "unresolvable" else outside).add(
                    str(reference)
                )
                name = _reference_basename(str(reference))
                if name:
                    ambiguous_names.add(name)
    return referenced, unresolvable, outside, legacy, ambiguous_names


def inspect_upload_cleanup(db: Session, upload_root: Path) -> UploadCleanupReport:
    """Classify files and references without mutating either database or disk."""
    (
        referenced,
        unresolvable,
        outside,
        legacy,
        ambiguous_names,
    ) = _product_reference_paths(db, upload_root)
    metadata: dict[Path, UploadAsset] = {}
    stale_metadata: list[UploadCleanupItem] = []
    for asset in db.scalars(select(UploadAsset)).all():
        path, status = _reference_to_path(asset.path, upload_root)
        if status == "ok" and path is not None:
            metadata[path] = asset
            if not path.exists() and path not in referenced:
                stale_metadata.append(
                    _cleanup_item(
                        path, upload_root, "managed", "missing_file_no_product_reference"
                    )
                )
        elif status in {"unresolvable", "outside_root", "external_legacy"}:
            unresolvable.add(f"metadata:{asset.path}")
            name = _reference_basename(asset.path)
            if name:
                ambiguous_names.add(name)

    broken: list[str] = []
    for path, product_ids in referenced.items():
        if not path.exists():
            ids = ",".join(str(value) for value in sorted(product_ids))
            broken.append(f"{_relative_upload_path(path, upload_root)} (products: {ids})")

    candidates: list[UploadCleanupItem] = []
    protected: list[UploadCleanupItem] = []
    try:
        disk_paths = sorted(
            upload_root.rglob("*"), key=lambda item: str(item).lower()
        )
    except OSError:
        disk_paths = []
    for disk_path in disk_paths:
        try:
            if not disk_path.is_file():
                continue
            resolved = disk_path.resolve(strict=False)
            root_resolved = upload_root.resolve(strict=False)
        except (OSError, RuntimeError):
            unresolvable.add(str(disk_path))
            continue
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            outside.add(str(disk_path))
            continue
        if resolved in referenced:
            ids = ",".join(str(value) for value in sorted(referenced[resolved]))
            kind = "managed" if resolved in metadata else "legacy"
            protected.append(_cleanup_item(resolved, upload_root, kind, f"product_reference:{ids}"))
        elif resolved in metadata:
            candidates.append(
                _cleanup_item(
                    resolved,
                    upload_root,
                    "managed",
                    "managed_file_no_product_reference",
                )
            )
        elif resolved.name in ambiguous_names:
            protected.append(
                _cleanup_item(
                    resolved, upload_root, "legacy", "unresolvable_reference_preserved"
                )
            )
        else:
            candidates.append(
                _cleanup_item(
                    resolved, upload_root, "legacy", "unreferenced_generated_file"
                )
            )

    key = lambda item: item.relative_path.lower()
    return UploadCleanupReport(
        dry_run=True,
        candidates=sorted(candidates, key=key),
        protected=sorted(protected, key=key),
        broken_references=sorted(broken),
        legacy_references=sorted(legacy),
        stale_metadata=sorted(stale_metadata, key=key),
        unresolvable_references=sorted(unresolvable),
        outside_root=sorted(outside),
    )


def _asset_for_path(
    db: Session, upload_root: Path, path: Path
) -> UploadAsset | None:
    resolved = path.resolve(strict=False)
    for asset in db.scalars(select(UploadAsset)).all():
        asset_path, status = _reference_to_path(asset.path, upload_root)
        if status == "ok" and asset_path == resolved:
            return asset
    return None


def _record_cleanup_failure_once(
    db: Session, upload_root: Path, actor_id: int | None, path: Path, error: Exception
) -> None:
    relative = _relative_upload_path(path, upload_root)
    existing = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "upload.cleanup_failed",
            AuditLog.target_id == relative,
        )
    )
    if existing is not None:
        return
    audit(
        db,
        "upload.cleanup_failed",
        actor_id=actor_id,
        target_type="upload_assets",
        target_id=relative,
        reason=str(error)[:240],
    )


def cleanup_upload_orphans(
    db: Session,
    upload_root: Path,
    actor_id: int | None,
    dry_run: bool = True,
    only_paths: Iterable[Path] | None = None,
) -> UploadCleanupReport:
    report = inspect_upload_cleanup(db, upload_root)
    if dry_run:
        return report
    report.dry_run = False

    if only_paths is not None:
        wanted = {Path(path).resolve(strict=False) for path in only_paths}
        report.candidates = [
            item
            for item in report.candidates
            if Path(item.path).resolve(strict=False) in wanted
        ]
        report.stale_metadata = []

    deleted: list[str] = []
    failed: list[str] = []
    for item in list(report.candidates):
        path = Path(item.path)
        if not path.exists():
            continue
        fresh = inspect_upload_cleanup(db, upload_root)
        fresh_candidates = {
            Path(candidate.path).resolve(strict=False)
            for candidate in fresh.candidates
        }
        if path.resolve(strict=False) not in fresh_candidates:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            failed.append(item.path)
            _record_cleanup_failure_once(db, upload_root, actor_id, path, exc)
            continue
        deleted.append(item.path)
        asset = _asset_for_path(db, upload_root, path)
        if asset is not None:
            db.delete(asset)

    if only_paths is None:
        for item in list(report.stale_metadata):
            fresh = inspect_upload_cleanup(db, upload_root)
            if item.path not in {candidate.path for candidate in fresh.stale_metadata}:
                continue
            asset = _asset_for_path(db, upload_root, Path(item.path))
            if asset is not None:
                db.delete(asset)
                deleted.append(item.path)

    if deleted:
        audit(
            db,
            "upload.orphan_cleanup",
            actor_id=actor_id,
            target_type="upload_assets",
            metadata={"deleted": len(deleted), "paths": deleted, "dry_run": False},
        )
    db.commit()
    report.deleted = deleted
    report.failed = failed
    return report


def upload_paths_for_references(
    db: Session, upload_root: Path, references: Any
) -> list[Path]:
    """Return managed asset paths that correspond to the supplied image refs."""
    wanted: set[Path] = set()
    for reference in _reference_strings(references):
        path, status = _reference_to_path(reference, upload_root)
        if status == "ok" and path is not None:
            wanted.add(path)
    result: list[Path] = []
    for asset in db.scalars(select(UploadAsset)).all():
        path, status = _reference_to_path(asset.path, upload_root)
        if status == "ok" and path in wanted:
            result.append(path)
    return result


def expire_reservations(db: Session, user_id: int | None = None) -> int:
    """Release expired holds and return the number released."""
    now = utcnow()
    query = select(Reservation).where(
        Reservation.status == "active",
        Reservation.expires_at <= now,
    )
    if user_id is not None:
        query = query.where(Reservation.user_id == user_id)
    rows = list(db.scalars(query).all())
    for row in rows:
        changed = db.execute(
            update(Reservation)
            .where(Reservation.id == row.id, Reservation.status == "active")
            .values(status="expired", released_at=now)
        )
        if changed.rowcount != 1:
            continue
        db.execute(
            update(Product)
            .where(Product.id == row.product_id)
            .values(
                reserved_stock=case(
                    (Product.reserved_stock >= row.quantity, Product.reserved_stock - row.quantity),
                    else_=0,
                )
            )
        )
    if rows:
        db.flush()
    return len(rows)


def reservation_expires_at(minutes: int = 15) -> datetime:
    return utcnow() + timedelta(minutes=minutes)
