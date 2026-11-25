"""Event collection and consent-aware, eligibility-filtered recommendations."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession, OptionalUser, require_admin
from ..models import Product, RecommendationEvent, RecommendationDatasetSnapshot
from ..schemas import Message, RecommendationEventIn, RecommendationList, RecommendationOut, RecommendationSnapshotOut
from ..services import audit, create_recommendation_snapshot, product_is_eligible, purge_recommendation_events
from ..utils import utcnow

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
admin_router = APIRouter(prefix="/admin/recommendations", tags=["admin"])

EVENT_WEIGHTS = {
    "PRODUCT_VIEW": 0.5,
    "FAVORITE_ADD": 3.0,
    "CART_ADD": 2.0,
    "DISMISS": -4.0,
}


@router.post("/events", response_model=Message, status_code=status.HTTP_201_CREATED)
def record_event(payload: RecommendationEventIn, user: OptionalUser, db: DbSession) -> Message:
    if user and not user.consent:
        return Message(message="Event not recorded because personalization consent is disabled")
    if not user and payload.event_type not in {
        "PRODUCT_VIEW",
        "RECOMMENDATION_IMPRESSION",
        "RECOMMENDATION_CLICK",
    }:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required for this event type",
        )
    product = db.get(Product, payload.product_id)
    if not product or not product_is_eligible(db, product):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if payload.event_type == "RECOMMENDATION_IMPRESSION" and not payload.recommendation_request_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recommendation impressions require a request id",
        )
    event_id = payload.event_id or secrets.token_hex(12)
    existing = db.scalar(select(RecommendationEvent).where(RecommendationEvent.event_id == event_id))
    if existing:
        if (
            existing.product_id != product.id
            or existing.user_id != (user.id if user else None)
            or existing.event_type != payload.event_type
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Event ID was already used for a different event",
            )
        return Message(message="Event already recorded")
    db.add(
        RecommendationEvent(
            event_id=event_id,
            user_id=user.id if user else None,
            product_id=product.id,
            event_type=payload.event_type,
            weight=payload.weight * EVENT_WEIGHTS.get(payload.event_type, 1.0),
            occurred_at=payload.occurred_at or utcnow(),
            received_at=utcnow(),
            session_id=payload.session_id,
            source_context=payload.source_context,
            recommendation_request_id=payload.recommendation_request_id,
            model_version=payload.model_version,
            position=payload.position,
            consent_snapshot=bool(user and user.consent),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(
            select(RecommendationEvent).where(RecommendationEvent.event_id == event_id)
        )
        if duplicate and (
            duplicate.product_id != product.id
            or duplicate.user_id != (user.id if user else None)
            or duplicate.event_type != payload.event_type
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Event ID was already used for a different event",
            )
        return Message(message="Event already recorded")
    return Message(message="Event recorded")


@router.get("", response_model=RecommendationList)
def recommend(
    user: OptionalUser,
    db: DbSession,
    limit: int = 9,
    product_id: int | None = None,
) -> RecommendationList:
    limit = min(max(limit, 1), 24)
    candidates = list(
        db.scalars(
            select(Product).where(
                Product.status == "Published",
                Product.stock > Product.reserved_stock,
            )
        ).all()
    )
    if product_id:
        candidates = [p for p in candidates if p.id != product_id]

    dismissed: set[int] = set()
    signals: list[tuple[Product, float]] = []
    if user and user.consent:
        events = db.scalars(
            select(RecommendationEvent).where(
                RecommendationEvent.user_id == user.id
            ).order_by(RecommendationEvent.created_at.desc()).limit(500)
        ).all()
        source_products = {
            product.id: product
            for product in db.scalars(
                select(Product).where(
                    Product.id.in_({event.product_id for event in events})
                )
            ).all()
        }
        for event in events:
            product = source_products.get(event.product_id)
            if not product:
                continue
            if event.event_type == "DISMISS":
                dismissed.add(product.id)
                continue
            signals.append((product, event.weight))

    candidates = [p for p in candidates if p.id not in dismissed and product_is_eligible(db, p)]
    scored: list[tuple[Product, float, str]] = []
    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []
        for source, weight in signals:
            match = 0.0
            if source.category == candidate.category:
                match += 3.0
                reasons.append("Similar saved category")
            if source.material and source.material == candidate.material:
                match += 2.0
            if source.style and source.style == candidate.style:
                match += 1.0
            if source.artisan == candidate.artisan:
                match += 2.0
                reasons.append("From a studio you follow")
            score += match * weight
        score += (0.15 if candidate.featured else 0.0) + (candidate.rating / 50.0)
        reason = reasons[0] if reasons else ("General pick" if not signals else "Handmade pick")
        scored.append((candidate, round(score, 3), reason))

    scored.sort(key=lambda row: (-row[1], row[0].id))
    chosen = scored[:limit]
    return RecommendationList(
        items=[
            RecommendationOut(
                id=product.id,
                slug=product.slug,
                name=product.name,
                image=product.image,
                price=product.price,
                category=product.category,
                artisan=product.artisan,
                score=score,
                reason=reason,
            )
            for product, score, reason in chosen
        ]
    )


@admin_router.post("/retention-cleanup", response_model=Message)
def retention_cleanup(
    user: CurrentUser, db: DbSession, retention_days: int = 90, _=Depends(require_admin)
) -> Message:
    if retention_days < 1 or retention_days > 3650:
        raise HTTPException(status_code=400, detail="Invalid retention period")
    deleted = purge_recommendation_events(db, retention_days, user.id)
    db.commit()
    return Message(message=f"Deleted {deleted} expired recommendation events")


@admin_router.post("/snapshots", response_model=RecommendationSnapshotOut, status_code=201)
def create_snapshot(
    user: CurrentUser, db: DbSession, _=Depends(require_admin)
) -> RecommendationSnapshotOut:
    snapshot = create_recommendation_snapshot(db, user.id)
    db.commit()
    db.refresh(snapshot)
    return RecommendationSnapshotOut.model_validate(snapshot)
