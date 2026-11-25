"""Saved-products endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession
from ..models import Favorite, Product
from ..schemas import FavoriteIds, FavoriteOut, FavoriteToggle, Message
from ..services import product_is_eligible

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _saved_ids(db: DbSession, user_id: int) -> list[int]:
    return list(
        db.scalars(
            select(Favorite.product_id)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
        ).all()
    )


def _ensure_product(db: DbSession, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or not product_is_eligible(db, product):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("/ids", response_model=FavoriteIds)
def get_saved_ids(user: CurrentUser, db: DbSession) -> FavoriteIds:
    return FavoriteIds(ids=_saved_ids(db, user.id))


@router.get("", response_model=list[FavoriteOut])
def get_favorites(user: CurrentUser, db: DbSession, limit: int = 100) -> list[FavoriteOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(
        select(Favorite)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
        .limit(limit)
    ).all()
    return [FavoriteOut.model_validate(row) for row in rows]


@router.post("/toggle/{product_id}", response_model=FavoriteToggle)
def toggle_favorite(product_id: int, user: CurrentUser, db: DbSession) -> FavoriteToggle:
    _ensure_product(db, product_id)
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if existing:
        db.delete(existing)
        favorited = False
    else:
        db.add(Favorite(user_id=user.id, product_id=product_id))
        favorited = True
    db.commit()
    return FavoriteToggle(favorited=favorited, ids=_saved_ids(db, user.id))


@router.post("/{product_id}", response_model=FavoriteToggle)
def add_favorite(product_id: int, user: CurrentUser, db: DbSession) -> FavoriteToggle:
    _ensure_product(db, product_id)
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if not existing:
        db.add(Favorite(user_id=user.id, product_id=product_id))
        db.commit()
    return FavoriteToggle(favorited=True, ids=_saved_ids(db, user.id))


@router.delete("/{product_id}", response_model=Message)
def remove_favorite(product_id: int, user: CurrentUser, db: DbSession) -> Message:
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id)
    )
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")
    db.delete(existing)
    db.commit()
    return Message(message="Removed from saved products")
