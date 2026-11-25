"""Checkout, parent orders, seller orders, and payments."""
from __future__ import annotations

import hashlib
import json
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession, require_admin, require_seller
from ..models import (
    CartItem,
    Order,
    OrderItem,
    Payment,
    Product,
    RecommendationEvent,
    Reservation,
    Refund,
    SellerOrder,
    User,
)
from ..schemas import CheckoutRequest, Message, OrderList, OrderOut, PaymentOut, SellerOrderOut
from ..services import audit, notify, product_is_eligible
from ..utils import add_money, cents_to_money, money_to_cents, multiply_money, order_number, round_money, utcnow

router = APIRouter(prefix="/orders", tags=["orders"])

SHIPPING_RATES = {
    "Morrow Clay Studio": 8.0,
    "Aster Metalworks": 5.0,
    "Kindred Flame": 6.0,
    "North Loop Knits": 7.0,
    "Field Note Stitchery": 7.0,
    "Thread & Timber": 9.0,
}
DEFAULT_SHIPPING = 7.0
TAX_RATE = 0.0
ACTIVE_RESERVATION_STATES = {"Awaiting Processing", "Processing"}


def _shipping(seller_name: str) -> float:
    return SHIPPING_RATES.get(seller_name, DEFAULT_SHIPPING)


def _derive_parent_status(order: Order) -> str:
    states = [child.status for child in order.seller_orders]
    if not states:
        return "Awaiting processing"
    if all(s == "Delivered" for s in states):
        return "Delivered"
    if all(s == "Cancelled" for s in states):
        return "Cancelled"
    if any(s == "Shipped" for s in states):
        return "Partially shipped"
    if any(s == "Processing" for s in states):
        return "Processing"
    return "Awaiting processing"


def _order_out(order: Order) -> OrderOut:
    payload = OrderOut.model_validate(order)
    payload.status = _derive_parent_status(order)
    return payload


def _seller_out(row: SellerOrder) -> SellerOrderOut:
    return SellerOrderOut.model_validate(row)


def _consume_reservations(
    db: DbSession, user_id: int, tokens: list[str], lines: dict[int, int]
) -> None:
    now = utcnow()
    consumed_by_product: dict[int, int] = {}
    for token in dict.fromkeys(tokens):
        reservation = db.scalar(select(Reservation).where(Reservation.token == token))
        if not reservation:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid reservation: {token}")
        if reservation.user_id != user_id or reservation.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid reservation: {token}")
        if reservation.expires_at <= now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Reservation expired: {token}")
        consumed_by_product[reservation.product_id] = (
            consumed_by_product.get(reservation.product_id, 0) + reservation.quantity
        )
        if lines.get(reservation.product_id, 0) < consumed_by_product[reservation.product_id]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation quantity exceeds purchased quantity",
            )
        changed = db.execute(
            update(Reservation)
            .where(
                Reservation.id == reservation.id,
                Reservation.status == "active",
                Reservation.expires_at > now,
            )
            .values(status="committed", released_at=now)
        )
        if changed.rowcount != 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reservation changed")
        db.execute(
            update(Product)
            .where(Product.id == reservation.product_id)
            .values(
                reserved_stock=case(
                    (Product.reserved_stock >= reservation.quantity,
                     Product.reserved_stock - reservation.quantity),
                    else_=0,
                )
            )
        )


@router.post("/checkout", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def checkout(
    payload: CheckoutRequest,
    user: CurrentUser,
    db: DbSession,
    x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OrderOut:
    if payload.payment_method != "sandbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the sandbox payment method is available",
        )
    if payload.address.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shipping contact email must match the authenticated account",
        )
    key = payload.idempotency_key or x_idempotency_key or secrets.token_hex(12)
    request_data = payload.model_dump(mode="json")
    request_data.pop("idempotency_key", None)
    request_hash = hashlib.sha256(
        json.dumps(request_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.operation == "checkout",
            Payment.idempotency_key == key,
        )
    )
    if existing and existing.order:
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used with a different request",
            )
        return _order_out(existing.order)

    if payload.items:
        selected_lines: list[tuple[Product, int]] = []
        for line in payload.items:
            product = db.get(Product, line.product_id)
            if not product or not product_is_eligible(db, product):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            if line.quantity > product.available_stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Only {product.available_stock} of {product.name} available",
                )
            selected_lines.append((product, line.quantity))
    else:
        rows = list(
            db.scalars(
                select(CartItem).where(
                    CartItem.user_id == user.id, CartItem.selected.is_(True)
                )
            ).all()
        )
        if not rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty")
        selected_lines = []
        for row in rows:
            product = db.get(Product, row.product_id)
            if not product or not product_is_eligible(db, product):
                continue
            quantity = min(row.quantity, product.available_stock)
            if quantity > 0:
                selected_lines.append((product, quantity))

    if not selected_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No items to checkout")

    aggregated: dict[int, tuple[Product, int]] = {}
    for product, quantity in selected_lines:
        if product.id in aggregated:
            _, previous = aggregated[product.id]
            aggregated[product.id] = (product, previous + quantity)
        else:
            aggregated[product.id] = (product, quantity)
    selected_lines = list(aggregated.values())
    reservation_rows = list(
        db.scalars(
            select(Reservation).where(
                Reservation.token.in_(list(dict.fromkeys(payload.reservation_tokens))),
                Reservation.user_id == user.id,
                Reservation.status == "active",
                Reservation.expires_at > utcnow(),
            )
        ).all()
    )
    reserved_for_checkout: dict[int, int] = {}
    for reservation in reservation_rows:
        reserved_for_checkout[reservation.product_id] = (
            reserved_for_checkout.get(reservation.product_id, 0) + reservation.quantity
        )
    for product, quantity in selected_lines:
        available_to_user = product.available_stock + reserved_for_checkout.get(product.id, 0)
        if quantity > available_to_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Stock changed for {product.name}; please review your cart",
            )

    reserved_by_product = {p.id: q for p, q in selected_lines}
    _consume_reservations(db, user.id, payload.reservation_tokens, reserved_by_product)

    grouped: dict[int, list[tuple[Product, int]]] = {}
    for product, quantity in selected_lines:
        if product.artisan_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product has no authoritative seller",
            )
        grouped.setdefault(product.artisan_id, []).append((product, quantity))

    subtotal_cents = sum(p.price_cents * q for p, q in selected_lines)
    subtotal = cents_to_money(subtotal_cents)
    seller_rows: list[dict] = []
    for seller_user_id, lines in grouped.items():
        seller = db.get(User, seller_user_id)
        seller_name = seller.studio_name if seller else lines[0][0].artisan
        seller_subtotal_cents = sum(p.price_cents * q for p, q in lines)
        seller_subtotal = cents_to_money(seller_subtotal_cents)
        seller_rows.append(
            {
                "seller": seller_name,
                "seller_user_id": seller_user_id,
                "subtotal": seller_subtotal,
                "subtotal_cents": seller_subtotal_cents,
                "shipping": _shipping(seller_name),
                "lines": lines,
            }
        )
    shipping_cents = sum(money_to_cents(row["shipping"]) for row in seller_rows)
    shipping = cents_to_money(shipping_cents)
    tax = multiply_money(subtotal, TAX_RATE) if TAX_RATE else 0.0
    tax_cents = money_to_cents(tax)
    total_cents = subtotal_cents + shipping_cents + tax_cents
    total = cents_to_money(total_cents)

    address = payload.address.model_dump()
    order = Order(
        order_number=order_number(),
        user_id=user.id,
        status="Awaiting processing",
        currency="USD",
        subtotal=subtotal,
        subtotal_cents=subtotal_cents,
        shipping=shipping,
        shipping_cents=shipping_cents,
        tax=tax,
        tax_cents=tax_cents,
        total=total,
        total_cents=total_cents,
        customer_name=address["full_name"],
        customer_email=address["email"],
        shipping_address=address,
        payment_method=payload.payment_method,
        items_snapshot=[],
    )
    db.add(order)
    db.flush()

    flat_items: list[dict] = []
    for row in seller_rows:
        seller_order = SellerOrder(
            order_id=order.id,
            seller_order_number=f"SO-{secrets.token_hex(5).upper()}",
            seller_name=row["seller"],
            seller_user_id=row["seller_user_id"],
            status="Awaiting Processing",
            subtotal=row["subtotal"],
            shipping=row["shipping"],
                total=add_money(row["subtotal"], row["shipping"]),
                subtotal_cents=row["subtotal_cents"],
                shipping_cents=money_to_cents(row["shipping"]),
                total_cents=row["subtotal_cents"] + money_to_cents(row["shipping"]),
            items_snapshot=[],
        )
        db.add(seller_order)
        db.flush()

        snapshot: list[dict] = []
        for product, quantity in row["lines"]:
            line = OrderItem(
                order_id=order.id,
                seller_order_id=seller_order.id,
                product_id=product.id,
                product_slug=product.slug,
                name=product.name,
                image=product.image,
                unit_price=cents_to_money(product.price_cents),
                unit_price_cents=product.price_cents,
                quantity=quantity,
                line_total=cents_to_money(product.price_cents * quantity),
                line_total_cents=product.price_cents * quantity,
            )
            db.add(line)
            db.flush()
            entry = {
                "id": line.id,
                "name": line.name,
                "price": line.unit_price,
                "qty": line.quantity,
                "product_id": product.id,
            }
            snapshot.append(entry)
            flat_items.append(entry)
            changed = db.execute(
                update(Product)
                .where(Product.id == product.id, Product.stock >= quantity)
                .values(stock=Product.stock - quantity)
            )
            if changed.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Stock changed for {product.name}; please retry",
                )
        seller_order.items_snapshot = snapshot

    order.items_snapshot = flat_items
    for product, _quantity in selected_lines:
        db.add(
            RecommendationEvent(
                event_id=f"purchase:{order.order_number}:{product.id}",
                user_id=user.id,
                product_id=product.id,
                event_type="PURCHASE",
                weight=4.0,
                occurred_at=utcnow(),
                received_at=utcnow(),
                source_context="checkout",
                consent_snapshot=bool(user.consent),
            )
        )
    db.add(
            Payment(
            order_id=order.id,
            user_id=user.id,
            idempotency_key=key,
            operation="checkout",
            request_hash=request_hash,
            provider="sandbox",
            status="sandbox_succeeded",
                amount=total,
                amount_cents=total_cents,
            currency="USD",
            details={"method": payload.payment_method, "notes": payload.notes},
            verified_at=utcnow(),
        )
    )

    purchased_ids = {p.id for p, _ in selected_lines}
    for row in db.scalars(select(CartItem).where(CartItem.user_id == user.id)).all():
        if row.product_id in purchased_ids:
            db.delete(row)

    notify(db, user.id, f"Order {order.order_number} placed")
    audit(
        db,
        "order.created",
        actor_id=user.id,
        target_type="order",
        target_id=order.order_number,
        metadata={"total": total, "seller_orders": len(seller_rows)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Payment).where(
                Payment.user_id == user.id,
                Payment.operation == "checkout",
                Payment.idempotency_key == key,
            )
        )
        if existing and existing.order and existing.request_hash == request_hash:
            return _order_out(existing.order)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Checkout retry conflict",
        )
    db.refresh(order)
    return _order_out(order)


@router.get("", response_model=OrderList)
def list_orders(user: CurrentUser, db: DbSession, limit: int = 100) -> OrderList:
    limit = min(max(limit, 1), 500)
    orders = list(
        db.scalars(
            select(Order).where(Order.user_id == user.id).order_by(Order.placed_at.desc()).limit(limit)
        ).all()
    )
    return OrderList(items=[_order_out(o) for o in orders], total=len(orders))


@router.get("/seller/orders", response_model=list[SellerOrderOut])
def seller_orders(
    user: CurrentUser, db: DbSession, limit: int = 100, _=Depends(require_seller)
) -> list[SellerOrderOut]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(
        select(SellerOrder)
        .where(SellerOrder.seller_user_id == user.id)
        .order_by(SellerOrder.created_at.desc())
        .limit(limit)
    ).all()
    return [_seller_out(row) for row in rows]


@router.get("/{reference}", response_model=OrderOut)
def get_order(reference: str, user: CurrentUser, db: DbSession) -> OrderOut:
    query = select(Order).where(Order.order_number == reference)
    if user.role != "admin":
        query = query.where(Order.user_id == user.id)
    order = db.scalar(query)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return _order_out(order)


@router.patch("/seller/{reference}/status", response_model=SellerOrderOut)
def advance_seller_order(
    reference: str, next_status: str, user: CurrentUser, db: DbSession,
    _=Depends(require_seller),
) -> SellerOrderOut:
    child = db.scalar(select(SellerOrder).where(SellerOrder.seller_order_number == reference))
    if not child:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller order not found")
    allowed_owner = child.seller_user_id == user.id
    if user.role != "admin" and not allowed_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your seller order")
    allowed = {
        "Awaiting Processing": {"Processing"},
        "Processing": {"Shipped"},
        "Shipped": {"Delivered"} if user.role == "admin" else set(),
    }
    if next_status not in allowed.get(child.status, set()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid fulfillment transition")
    old_status = child.status
    child.status = next_status
    audit(
        db,
        "seller_order.status_change",
        actor_id=user.id,
        target_type="seller_order",
        target_id=child.seller_order_number,
        metadata={"from": old_status, "to": next_status},
    )
    parent = db.get(Order, child.order_id)
    if parent:
        notify(db, parent.user_id, f"Seller order {child.seller_order_number} is now {next_status}")
    db.commit()
    db.refresh(child)
    return _seller_out(child)


@router.post("/seller/{reference}/cancel", response_model=SellerOrderOut)
def cancel_seller_order(reference: str, user: CurrentUser, db: DbSession) -> SellerOrderOut:
    child = db.scalar(select(SellerOrder).where(SellerOrder.seller_order_number == reference))
    if not child:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller order not found")
    parent = db.get(Order, child.order_id)
    if not parent or (parent.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    if child.status not in ACTIVE_RESERVATION_STATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This seller order can no longer be cancelled")
    old_status = child.status
    child.status = "Cancelled"
    for item in child.items:
        if item.product_id:
            db.execute(
                update(Product)
                .where(Product.id == item.product_id)
                .values(stock=Product.stock + item.quantity)
            )
    if parent.payment:
        existing_refund = db.scalar(
            select(Refund).where(
                Refund.payment_id == parent.payment.id,
                Refund.seller_order_id == child.id,
            )
        )
        if existing_refund:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Refund already recorded")
        if child.total_cents <= 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid refund amount")
        refunded_already = sum(refund.amount_cents for refund in parent.payment.refunds)
        if refunded_already + child.total_cents > parent.payment.amount_cents:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Refund exceeds sandbox payment")
        db.add(
            Refund(
                payment_id=parent.payment.id,
                seller_order_id=child.id,
                idempotency_key=f"cancel:{child.seller_order_number}",
                amount_cents=child.total_cents,
                reason="seller_order_cancelled",
            )
        )
        details = dict(parent.payment.details or {})
        refunded_cents = refunded_already + child.total_cents
        details["refunded_cents"] = refunded_cents
        details["refunded_amount"] = cents_to_money(refunded_cents)
        details.setdefault("adjustments", []).append(
            {
                "seller_order": child.seller_order_number,
                "amount_cents": child.total_cents,
            }
        )
        parent.payment.details = details
        parent.payment.status = (
            "sandbox_refunded"
            if refunded_cents >= parent.total_cents
            else "sandbox_partially_refunded"
        )
        parent.payment.verified_at = utcnow()
    audit(
        db,
        "seller_order.cancelled",
        actor_id=user.id,
        target_type="seller_order",
        target_id=child.seller_order_number,
        metadata={"from": old_status},
    )
    notify(db, parent.user_id, f"Seller order {child.seller_order_number} cancelled")
    db.commit()
    db.refresh(child)
    return _seller_out(child)


@router.get("/payments/{order_reference}", response_model=PaymentOut)
def get_payment(order_reference: str, user: CurrentUser, db: DbSession) -> PaymentOut:
    order = db.scalar(select(Order).where(Order.order_number == order_reference))
    if not order or (order.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if not order.payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentOut.model_validate(order.payment)


@router.patch("/{reference}/status", response_model=OrderOut, dependencies=[Depends(require_admin)])
def update_order_status(reference: str, status_value: str, user: CurrentUser, db: DbSession) -> OrderOut:
    order = db.scalar(select(Order).where(Order.order_number == reference))
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    child_states = [child.status for child in order.seller_orders]
    allowed = {"Awaiting processing", "Processing", "Partially shipped", "Delivered", "Cancelled"}
    if status_value not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    current_status = _derive_parent_status(order)
    if status_value != current_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent order status is derived from seller orders",
        )
    audit(
        db,
        "order.status_change",
        actor_id=user.id,
        target_type="order",
        target_id=order.order_number,
        metadata={"from": _derive_parent_status(order), "to": status_value, "children": child_states},
    )
    notify(db, order.user_id, f"Order {order.order_number} status is {status_value}")
    db.commit()
    return _order_out(order)
