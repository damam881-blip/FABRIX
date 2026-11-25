"""Cross-cutting backend services used by multiple routers."""
from __future__ import annotations

from datetime import timedelta
import secrets
from pathlib import Path
import hashlib
from typing import Any

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

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


def upload_orphans(db: Session, upload_root: Path) -> list[Path]:
    referenced = {
        Path(path).resolve()
        for path in db.scalars(select(UploadAsset.path)).all()
    }
    return [
        path for path in upload_root.rglob("*")
        if path.is_file() and path.resolve() not in referenced
    ]


def cleanup_upload_orphans(
    db: Session, upload_root: Path, actor_id: int | None, dry_run: bool = True
) -> int:
    orphans = upload_orphans(db, upload_root)
    if not dry_run:
        for path in orphans:
            path.unlink(missing_ok=True)
        audit(
            db,
            "upload.orphan_cleanup",
            actor_id=actor_id,
            target_type="upload_assets",
            metadata={"deleted": len(orphans), "dry_run": False},
        )
        db.commit()
    return len(orphans)


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
