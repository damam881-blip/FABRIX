"""Server-side shopping cart endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession
from ..models import CartItem, Product
from ..schemas import CartItemCreate, CartItemOut, CartItemUpdate, CartOut, CartSyncIn, Message, ProductOut
from ..services import product_is_eligible
from ..utils import add_money, cents_to_money, multiply_money

router = APIRouter(prefix="/cart", tags=["cart"])


def _rows(db: DbSession, user_id: int) -> list[CartItem]:
    return list(
        db.scalars(
            select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.created_at)
        ).all()
    )


def _cart_out(db: DbSession, user_id: int) -> CartOut:
    rows = _rows(db, user_id)
    items = [
        CartItemOut(
            id=row.id,
            product_id=row.product_id,
            quantity=row.quantity,
            selected=row.selected,
            product=ProductOut.model_validate(row.product),
            line_total=cents_to_money(row.product.price_cents * row.quantity),
        )
        for row in rows
    ]
    subtotal = add_money(*(item.line_total for item in items))
    selected_subtotal = add_money(*(item.line_total for item in items if item.selected))
    return CartOut(
        items=items,
        count=sum(item.quantity for item in items),
        subtotal=subtotal,
        selected_subtotal=selected_subtotal,
    )


def _validate_product(db: DbSession, product_id: int, quantity: int) -> Product:
    product = db.get(Product, product_id)
    if not product or not product_is_eligible(db, product):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if quantity > product.available_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.available_stock} available",
        )
    return product


@router.get("", response_model=CartOut)
def get_cart(user: CurrentUser, db: DbSession) -> CartOut:
    return _cart_out(db, user.id)


@router.post("/add", response_model=CartOut)
def add_to_cart(payload: CartItemCreate, user: CurrentUser, db: DbSession) -> CartOut:
    _validate_product(db, payload.product_id, payload.quantity)
    existing = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == payload.product_id)
    )
    if existing:
        existing.quantity = min(existing.quantity + payload.quantity, 99)
        existing.selected = True
    else:
        db.add(CartItem(user_id=user.id, product_id=payload.product_id, quantity=payload.quantity))
    db.commit()
    return _cart_out(db, user.id)


@router.patch("/{product_id}", response_model=CartOut)
def update_cart_item(
    product_id: int, payload: CartItemUpdate, user: CurrentUser, db: DbSession
) -> CartOut:
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id)
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    if payload.quantity is not None:
        _validate_product(db, product_id, payload.quantity)
        item.quantity = payload.quantity
    if payload.selected is not None:
        item.selected = payload.selected
    db.commit()
    return _cart_out(db, user.id)


@router.delete("/{product_id}", response_model=CartOut)
def remove_cart_item(product_id: int, user: CurrentUser, db: DbSession) -> CartOut:
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id)
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return _cart_out(db, user.id)


@router.delete("", response_model=Message)
def clear_cart(user: CurrentUser, db: DbSession) -> Message:
    for item in _rows(db, user.id):
        db.delete(item)
    db.commit()
    return Message(message="Cart cleared")


@router.post("/sync", response_model=CartOut)
def sync_cart(payload: CartSyncIn, user: CurrentUser, db: DbSession) -> CartOut:
    """Replace the server cart with a browser-local cart (used for migration)."""
    for item in _rows(db, user.id):
        db.delete(item)
    db.flush()

    seen: set[int] = set()
    for line in payload.items:
        if line.product_id in seen:
            continue
        seen.add(line.product_id)
        product = db.get(Product, line.product_id)
        if product and product_is_eligible(db, product):
            db.add(
                CartItem(
                    user_id=user.id,
                    product_id=line.product_id,
                    quantity=min(line.quantity, product.available_stock),
                    selected=True,
                )
            )
    db.commit()
    return _cart_out(db, user.id)
