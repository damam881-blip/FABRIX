"""SQLAlchemy ORM models for FABRIX.

The schema mirrors the browser demo data while adding the server-authoritative
records the static prototype could not provide: stores, addresses, reservations,
payments, per-seller fulfillment, verified reviews, and audit trails.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .utils import utcnow


def _now() -> datetime:
    return utcnow()


PRODUCT_STATES = ("Draft", "Published", "Unpublished", "Blocked")
SELLER_ORDER_STATES = ("Awaiting Processing", "Processing", "Shipped", "Delivered", "Cancelled")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, default="FABRIX Customer")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="customer", index=True)
    can_shop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_sell: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    studio_name: Mapped[str | None] = mapped_column(String(160), index=True)
    studio_story: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    personalization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Notification.created_at.desc()"
    )
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    store: Mapped["Store | None"] = relationship(
        back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )
    seller_applications: Mapped[list["SellerApplication"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")
    reviews: Mapped[list["Review"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    line1: Mapped[str] = mapped_column(String(180), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(180))
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str | None] = mapped_column(String(80))
    postal_code: Mapped[str] = mapped_column(String(24), nullable=False)
    country: Mapped[str] = mapped_column(String(60), nullable=False, default="US")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="addresses")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="notifications")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    story: Mapped[str] = mapped_column(Text, nullable=False, default="")
    craft: Mapped[str] = mapped_column(String(120), nullable=False, default="Textiles")
    location: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="Draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="store")


class SellerApplication(Base):
    """Kept for compatibility with the original artisan entry form."""

    __tablename__ = "seller_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    studio_name: Mapped[str] = mapped_column(String(160), nullable=False)
    craft: Mapped[str] = mapped_column(String(120), nullable=False, default="Textiles")
    story: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="seller_applications")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_price_nonnegative"),
        CheckConstraint("stock >= 0", name="ck_product_stock_nonnegative"),
        CheckConstraint("reserved_stock >= 0", name="ck_product_reserved_nonnegative"),
        CheckConstraint("reserved_stock <= stock", name="ck_product_reserved_lte_stock"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    artisan: Mapped[str] = mapped_column(String(160), nullable=False, default="FABRIX Maker", index=True)
    studio: Mapped[str | None] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Home objects", index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compare_at_price: Mapped[float | None] = mapped_column(Float)
    compare_at_price_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    image: Mapped[str | None] = mapped_column(String(500))
    images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    material: Mapped[str | None] = mapped_column(String(80), index=True)
    style: Mapped[str | None] = mapped_column(String(80), index=True)
    color: Mapped[str | None] = mapped_column(String(80), index=True)
    tag: Mapped[str | None] = mapped_column(String(80))
    materials: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    reserved_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=4.8)
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft", index=True)
    artisan_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    favorites: Mapped[list["Favorite"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    cart_items: Mapped[list["CartItem"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="product")
    reviews: Mapped[list["Review"]] = relationship(back_populates="product")

    @property
    def available_stock(self) -> int:
        return max(int(self.stock) - int(self.reserved_stock or 0), 0)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="favorites")
    product: Mapped[Product] = relationship(back_populates="favorites")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        CheckConstraint("quantity > 0 AND quantity <= 99", name="ck_cart_quantity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="cart_items")
    product: Mapped[Product] = relationship(back_populates="cart_items")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_quantity_positive"),
    )

    user: Mapped[User] = relationship(back_populates="reservations")
    product: Mapped[Product] = relationship(back_populates="reservations")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_order_subtotal_nonnegative"),
        CheckConstraint("shipping >= 0", name="ck_order_shipping_nonnegative"),
        CheckConstraint("tax >= 0", name="ck_order_tax_nonnegative"),
        CheckConstraint("total >= 0", name="ck_order_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Awaiting processing", index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shipping: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_address: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(60), nullable=False, default="sandbox")
    items_snapshot: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    seller_orders: Mapped[list["SellerOrder"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="SellerOrder.id"
    )
    payment: Mapped["Payment | None"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def payment_status(self) -> str | None:
        return self.payment.status if self.payment else None


class SellerOrder(Base):
    __tablename__ = "seller_orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_seller_order_subtotal_nonnegative"),
        CheckConstraint("shipping >= 0", name="ck_seller_order_shipping_nonnegative"),
        CheckConstraint("total >= 0", name="ck_seller_order_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    seller_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    seller_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="Awaiting Processing", index=True)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shipping: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_snapshot: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="seller_orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="seller_order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("seller_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    product_slug: Mapped[str | None] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    image: Mapped[str | None] = mapped_column(String(500))
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_item_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_order_item_total_nonnegative"),
    )

    order: Mapped[Order] = relationship(back_populates="items")
    seller_order: Mapped[SellerOrder | None] = relationship(back_populates="items")
    reviews: Mapped[list["Review"]] = relationship(back_populates="order_item")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, default="checkout")
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="sandbox")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="paid", index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payment")
    user: Mapped[User] = relationship()
    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_payment_user_operation_key",
        ),
        CheckConstraint("amount >= 0", name="ck_payment_amount_nonnegative"),
    )


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("payment_id", "idempotency_key", name="uq_refund_payment_key"),
        CheckConstraint("amount_cents > 0", name="ck_refund_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("seller_orders.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="sandbox_succeeded")
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="refunds")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_review_order_item"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    seller_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("seller_orders.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="approved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="reviews")
    product: Mapped[Product] = relationship(back_populates="reviews")
    order_item: Mapped[OrderItem] = relationship(back_populates="reviews")
    reports: Mapped[list["ReviewReport"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (UniqueConstraint("review_id", "reporter_id", name="uq_review_reporter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    review: Mapped[Review] = relationship(back_populates="reports")


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_recommendation_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PRODUCT_VIEW", index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_context: Mapped[str | None] = mapped_column(String(120))
    recommendation_request_id: Mapped[str | None] = mapped_column(String(120), index=True)
    model_version: Mapped[str | None] = mapped_column(String(80))
    position: Mapped[int | None] = mapped_column(Integer)
    consent_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class RecommendationDatasetSnapshot(Base):
    __tablename__ = "recommendation_dataset_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    taxonomy_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    criteria: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    included_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exclusion_reasons: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UploadAsset(Base):
    __tablename__ = "upload_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(60), index=True)
    target_id: Mapped[str | None] = mapped_column(String(80), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    actor: Mapped[User | None] = relationship(back_populates="audit_logs")


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
