"""Short-lived inventory reservations (15-minute holds)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession
from ..models import Product, Reservation
from ..schemas import Message, ReservationCreate, ReservationOut
from ..services import expire_reservations, product_is_eligible, reservation_expires_at

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: ReservationCreate, user: CurrentUser, db: DbSession) -> ReservationOut:
    expire_reservations(db)
    product = db.get(Product, payload.product_id)
    if not product or not product_is_eligible(db, product):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    changed = db.execute(
        update(Product)
        .where(
            Product.id == product.id,
            Product.status == "Published",
            Product.stock - Product.reserved_stock >= payload.quantity,
        )
        .values(reserved_stock=Product.reserved_stock + payload.quantity)
    )
    if changed.rowcount != 1:
        db.rollback()
        product = db.get(Product, payload.product_id)
        available = product.available_stock if product else 0
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only {available} available",
        )
    row = Reservation(
        token=secrets.token_urlsafe(24),
        user_id=user.id,
        product_id=product.id,
        quantity=payload.quantity,
        expires_at=reservation_expires_at(payload.duration_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ReservationOut.model_validate(row)


@router.get("", response_model=list[ReservationOut])
def list_reservations(user: CurrentUser, db: DbSession, limit: int = 100) -> list[ReservationOut]:
    limit = min(max(limit, 1), 500)
    expire_reservations(db)
    rows = db.scalars(
        select(Reservation)
        .where(Reservation.user_id == user.id)
        .order_by(Reservation.created_at.desc())
        .limit(limit)
    ).all()
    return [ReservationOut.model_validate(row) for row in rows]


@router.delete("/{token}", response_model=Message)
def release_reservation(token: str, user: CurrentUser, db: DbSession) -> Message:
    row = db.scalar(
        select(Reservation).where(Reservation.token == token, Reservation.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    if row.status == "active":
        from ..utils import utcnow

        now = utcnow()
        changed = db.execute(
            update(Reservation)
            .where(Reservation.id == row.id, Reservation.status == "active")
            .values(status="released", released_at=now)
        )
        if changed.rowcount == 1:
            db.execute(
                update(Product)
                .where(Product.id == row.product_id)
                .values(
                    reserved_stock=case(
                        (Product.reserved_stock >= row.quantity,
                         Product.reserved_stock - row.quantity),
                        else_=0,
                    )
                )
            )
        db.commit()
    return Message(message="Reservation released")
