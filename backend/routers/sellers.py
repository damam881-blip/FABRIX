"""Artisan studio lifecycle and admin approval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession, require_admin
from ..models import Product, SellerOrder, Store, User
from ..schemas import (
    AdminStats,
    AuditLogList,
    AuditLogOut,
    Message,
    ProductOut,
    SellerOrderOut,
    StoreDecisionIn,
    StoreIn,
    StoreOut,
)
from ..services import audit, notify
from ..services import cleanup_upload_orphans, upload_orphans
from ..utils import round_money, utcnow
from sqlalchemy import func

router = APIRouter(prefix="/seller", tags=["seller"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

VALID_TRANSITIONS = {
    "Draft": {"Pending"},
    "Changes Requested": {"Pending"},
    "Pending": {"Approved", "Changes Requested"},
    "Approved": {"Suspended"},
    "Suspended": {"Approved", "Changes Requested"},
}


def _store_out(row: Store) -> StoreOut:
    return StoreOut.model_validate(row)


@router.get("/store", response_model=StoreOut)
def get_my_store(user: CurrentUser, db: DbSession) -> StoreOut:
    store = db.scalar(select(Store).where(Store.user_id == user.id))
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Studio not found")
    return _store_out(store)


@router.post("/store", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
def create_store(payload: StoreIn, user: CurrentUser, db: DbSession) -> StoreOut:
    existing = db.scalar(select(Store).where(Store.user_id == user.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Studio already exists")
    store = Store(user_id=user.id, state="Draft", **payload.model_dump())
    if user.role == "customer":
        user.role = "artisan"
        user.can_sell = False
    db.add(store)
    db.commit()
    db.refresh(store)
    return _store_out(store)


@router.patch("/store", response_model=StoreOut)
def update_store(payload: StoreIn, user: CurrentUser, db: DbSession) -> StoreOut:
    store = db.scalar(select(Store).where(Store.user_id == user.id))
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Studio not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return _store_out(store)


@router.post("/store/submit", response_model=StoreOut)
def submit_store(user: CurrentUser, db: DbSession) -> StoreOut:
    store = db.scalar(select(Store).where(Store.user_id == user.id))
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Studio not found")
    if store.state not in {"Draft", "Changes Requested"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid store transition")
    if not store.name.strip() or not store.story.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete your studio name and story")
    store.state = "Pending"
    store.submitted_at = utcnow()
    notify(db, user.id, "Studio application submitted for review")
    db.commit()
    db.refresh(store)
    return _store_out(store)


@admin_router.get("/stores", response_model=list[StoreOut])
def list_stores(db: DbSession, limit: int = 100, _: User = Depends(require_admin)) -> list[StoreOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(select(Store).order_by(Store.created_at.desc()).limit(limit)).all()
    return [_store_out(row) for row in rows]


@admin_router.patch("/stores/{store_id}", response_model=StoreOut)
def decide_store(
    store_id: int,
    payload: StoreDecisionIn,
    user: CurrentUser,
    db: DbSession,
    _=Depends(require_admin),
) -> StoreOut:
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Studio not found")
    if payload.decision not in VALID_TRANSITIONS.get(store.state, set()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid store lifecycle transition")

    old_state = store.state
    store.state = payload.decision
    store.notes = payload.reason.strip()
    if payload.decision == "Approved":
        store.approved_at = utcnow()
    owner = db.get(User, store.user_id)
    if owner:
        if payload.decision == "Approved":
            owner.can_sell = True
            owner.role = "artisan" if owner.role == "customer" else owner.role
            owner.studio_name = store.name
            owner.studio_story = store.story
        elif payload.decision == "Suspended":
            owner.can_sell = False

    audit(
        db,
        "store.decision",
        actor_id=user.id,
        target_type="store",
        target_id=store.id,
        reason=payload.reason,
        metadata={"from": old_state, "to": payload.decision},
    )
    notify(db, store.user_id, f"Studio application: {payload.decision}")
    db.commit()
    db.refresh(store)
    return _store_out(store)


@admin_router.get("/stats", response_model=AdminStats)
def admin_stats(db: DbSession, _: User = Depends(require_admin)) -> AdminStats:
    from ..models import Order, Product, ReviewReport

    revenue = db.scalar(select(func.coalesce(func.sum(Order.total), 0.0))) or 0.0
    return AdminStats(
        users=int(db.scalar(select(func.count(User.id))) or 0),
        products=int(db.scalar(select(func.count(Product.id))) or 0),
        published_products=int(
            db.scalar(select(func.count(Product.id)).where(Product.status == "Published")) or 0
        ),
        orders=int(db.scalar(select(func.count(Order.id))) or 0),
        revenue=round_money(float(revenue)),
        pending_stores=int(
            db.scalar(select(func.count(Store.id)).where(Store.state == "Pending")) or 0
        ),
        pending_reports=int(
            db.scalar(select(func.count(ReviewReport.id)).where(ReviewReport.status == "pending")) or 0
        ),
    )


@admin_router.get("/products", response_model=list[ProductOut])
def admin_products(db: DbSession, limit: int = 100, _: User = Depends(require_admin)) -> list[ProductOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(select(Product).order_by(Product.created_at.desc()).limit(limit)).all()
    return [ProductOut.model_validate(row) for row in rows]


@admin_router.get("/seller-orders", response_model=list[SellerOrderOut])
def admin_seller_orders(db: DbSession, limit: int = 100, _: User = Depends(require_admin)) -> list[SellerOrderOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(select(SellerOrder).order_by(SellerOrder.created_at.desc()).limit(limit)).all()
    return [SellerOrderOut.model_validate(row) for row in rows]


@admin_router.get("/audit", response_model=AuditLogList)
def audit_log(db: DbSession, limit: int = 100, _: User = Depends(require_admin)) -> AuditLogList:
    from ..models import AuditLog

    rows = list(
        db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500))
        ).all()
    )
    return AuditLogList(items=[AuditLogOut.model_validate(row) for row in rows], total=len(rows))


@admin_router.post("/uploads/cleanup", response_model=Message)
def cleanup_uploads(
    user: CurrentUser,
    db: DbSession,
    dry_run: bool = True,
    _=Depends(require_admin),
) -> Message:
    from .products import UPLOAD_DIR

    if dry_run:
        count = len(upload_orphans(db, UPLOAD_DIR))
    else:
        count = cleanup_upload_orphans(db, UPLOAD_DIR, user.id, dry_run=False)
    return Message(message=f"{'Found' if dry_run else 'Deleted'} {count} orphan uploads")
