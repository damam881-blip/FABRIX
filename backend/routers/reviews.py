"""Verified reviews, reports, and admin moderation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession, require_admin
from ..models import Order, OrderItem, Product, Review, ReviewReport, SellerOrder, User
from ..schemas import (
    Message,
    ReviewCreate,
    ReviewList,
    ReviewOut,
    ReviewReportCreate,
    ReviewReportList,
    ReviewReportOut,
)
from ..services import audit, notify, recompute_product_rating
from ..utils import utcnow

router = APIRouter(prefix="/reviews", tags=["reviews"])
admin_router = APIRouter(prefix="/admin/reviews", tags=["admin"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(payload: ReviewCreate, user: CurrentUser, db: DbSession) -> ReviewOut:
    item = db.get(OrderItem, payload.order_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")
    order = db.get(Order, item.order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order item")
    child = db.get(SellerOrder, item.seller_order_id) if item.seller_order_id else None
    if not child or child.status != "Delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviews are only available for delivered seller orders",
        )
    product = db.get(Product, item.product_id) if item.product_id else None
    if product and product.artisan_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Artisans cannot review their own products",
        )
    existing = db.scalar(select(Review).where(Review.order_item_id == item.id))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This item was already reviewed")

    review = Review(
        user_id=user.id,
        product_id=item.product_id or 0,
        order_item_id=item.id,
        seller_order_id=child.id,
        rating=payload.rating,
        message=payload.message.strip(),
        author=user.full_name,
        status="approved",
    )
    db.add(review)
    db.flush()
    recompute_product_rating(db, review.product_id)
    audit(
        db,
        "review.created",
        actor_id=user.id,
        target_type="review",
        target_id=review.id,
        metadata={"product_id": review.product_id, "rating": review.rating},
    )
    db.commit()
    db.refresh(review)
    return ReviewOut.model_validate(review)


@router.get("/product/{product_id}", response_model=ReviewList)
def product_reviews(product_id: int, db: DbSession, limit: int = 100) -> ReviewList:
    limit = min(max(limit, 1), 500)
    rows = list(
        db.scalars(
            select(Review)
            .where(Review.product_id == product_id, Review.status == "approved")
            .order_by(Review.created_at.desc())
            .limit(limit)
        ).all()
    )
    average = round(sum(r.rating for r in rows) / len(rows), 2) if rows else 0.0
    return ReviewList(
        items=[ReviewOut.model_validate(row) for row in rows],
        total=len(rows),
        average=average,
    )


@router.get("/mine", response_model=list[ReviewOut])
def my_reviews(user: CurrentUser, db: DbSession, limit: int = 100) -> list[ReviewOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(
        select(Review).where(Review.user_id == user.id).order_by(Review.created_at.desc()).limit(limit)
    ).all()
    return [ReviewOut.model_validate(row) for row in rows]


@router.post("/{review_id}/report", response_model=ReviewReportOut, status_code=status.HTTP_201_CREATED)
def report_review(
    review_id: int, payload: ReviewReportCreate, user: CurrentUser, db: DbSession
) -> ReviewReportOut:
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    existing = db.scalar(
        select(ReviewReport).where(
            ReviewReport.review_id == review_id, ReviewReport.reporter_id == user.id
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already reported")
    row = ReviewReport(
        review_id=review_id,
        reporter_id=user.id,
        reason=payload.reason.strip(),
    )
    db.add(row)
    review.status = "reported"
    recompute_product_rating(db, review.product_id)
    db.commit()
    db.refresh(row)
    return ReviewReportOut.model_validate(row)


@admin_router.get("/reports", response_model=ReviewReportList)
def list_reports(db: DbSession, _: User = Depends(require_admin)) -> ReviewReportList:
    rows = list(
        db.scalars(
            select(ReviewReport)
            .where(ReviewReport.status == "pending")
            .order_by(ReviewReport.created_at.desc())
        ).all()
    )
    return ReviewReportList(items=[ReviewReportOut.model_validate(row) for row in rows], total=len(rows))


@admin_router.patch("/reports/{report_id}", response_model=ReviewReportOut)
def resolve_report(
    report_id: int, decision: str, user: CurrentUser, db: DbSession,
    _=Depends(require_admin),
) -> ReviewReportOut:
    if decision not in {"kept", "removed", "dismissed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid decision")
    row = db.get(ReviewReport, report_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    row.status = decision
    row.resolved_at = utcnow()
    review = db.get(Review, row.review_id)
    if review:
        review.status = "rejected" if decision == "removed" else "approved"
        recompute_product_rating(db, review.product_id)
    audit(
        db,
        "review_report.resolved",
        actor_id=user.id,
        target_type="review_report",
        target_id=row.id,
        metadata={"decision": decision},
    )
    if review:
        notify(db, review.user_id, f"Your review was reviewed: {decision}")
    db.commit()
    db.refresh(row)
    return ReviewReportOut.model_validate(row)
