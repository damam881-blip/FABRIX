"""Pydantic request and response schemas for the FABRIX API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Admin accounts are provisioned out-of-band and cannot be created through
# the public registration endpoint.
Role = Literal["customer", "artisan"]
ProductState = Literal["Draft", "Published", "Unpublished", "Blocked"]
SellerOrderState = Literal[
    "Awaiting Processing", "Processing", "Shipped", "Delivered", "Cancelled"
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Identity, profile, addresses, notifications
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(default="FABRIX Customer", min_length=2, max_length=120)
    role: Role = "customer"
    studio_name: str | None = Field(default=None, max_length=160)
    studio_story: str | None = Field(default=None, max_length=4000)
    consent: bool = True
    personalization: bool = True

    @field_validator("studio_name", "studio_story")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def bcrypt_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: Role | None = None


class UserOut(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    can_shop: bool
    can_sell: bool
    studio_name: str | None = None
    studio_story: str | None = None
    avatar_url: str | None = None
    personalization: bool
    consent: bool
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    studio_name: str | None = Field(default=None, max_length=160)
    studio_story: str | None = Field(default=None, max_length=4000)
    avatar_url: str | None = Field(default=None, max_length=500)
    personalization: bool | None = None
    consent: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AddressIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    line1: str = Field(min_length=3, max_length=180)
    line2: str | None = Field(default=None, max_length=180)
    city: str = Field(min_length=2, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    postal_code: str = Field(min_length=2, max_length=24)
    country: str = Field(default="US", max_length=60)
    is_default: bool = False


class AddressOut(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str | None = None
    line1: str
    line2: str | None = None
    city: str
    region: str | None = None
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime


class NotificationOut(ORMModel):
    id: int
    message: str
    is_read: bool
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductBase(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    artisan: str = Field(default="FABRIX Maker", max_length=160)
    studio: str | None = Field(default=None, max_length=160)
    category: str = Field(default="Home objects", max_length=80)
    price: float = Field(ge=0)
    compare_at_price: float | None = Field(default=None, ge=0)
    image: str | None = Field(default=None, max_length=500)
    images: list[str] = Field(default_factory=list)
    description: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    material: str | None = Field(default=None, max_length=80)
    style: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    tag: str | None = Field(default=None, max_length=80)
    materials: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    stock: int = Field(default=25, ge=0)
    rating: float = Field(default=4.8, ge=0, le=5)
    reviews_count: int = Field(default=0, ge=0)
    featured: bool = False
    status: ProductState = "Draft"

    @field_validator("price", "compare_at_price")
    @classmethod
    def cents_precision(cls, value: float | None) -> float | None:
        if value is not None and (Decimal(str(value)) * 100) % 1 != 0:
            raise ValueError("Money values must have at most two decimal places")
        return value


class ProductCreate(ProductBase):
    slug: str | None = Field(default=None, max_length=160)


class ProductUpdate(BaseModel):
    name: str | None = None
    artisan: str | None = None
    studio: str | None = None
    category: str | None = None
    price: float | None = Field(default=None, ge=0)
    compare_at_price: float | None = Field(default=None, ge=0)
    image: str | None = None
    images: list[str] | None = None
    description: str | None = None
    details: dict[str, Any] | None = None
    material: str | None = None
    style: str | None = None
    color: str | None = None
    tag: str | None = None
    materials: list[str] | None = None
    tags: list[str] | None = None
    stock: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    featured: bool | None = None
    status: ProductState | None = None

    @field_validator("price", "compare_at_price")
    @classmethod
    def cents_precision(cls, value: float | None) -> float | None:
        if value is not None and (Decimal(str(value)) * 100) % 1 != 0:
            raise ValueError("Money values must have at most two decimal places")
        return value


class ProductOut(ORMModel):
    id: int
    slug: str
    name: str
    artisan: str
    studio: str | None = None
    category: str
    price: float
    compare_at_price: float | None = None
    currency: str
    image: str | None = None
    images: list[str]
    description: str | None = None
    details: dict[str, Any]
    material: str | None = None
    style: str | None = None
    color: str | None = None
    tag: str | None = None
    materials: list[str]
    tags: list[str]
    stock: int
    available_stock: int
    rating: float
    reviews_count: int
    featured: bool
    status: str
    created_at: datetime


class ProductList(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    categories: list[str]


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


class FavoriteOut(ORMModel):
    id: int
    product_id: int
    created_at: datetime
    product: ProductOut


class FavoriteIds(BaseModel):
    ids: list[int]


class FavoriteToggle(BaseModel):
    favorited: bool
    ids: list[int]


# ---------------------------------------------------------------------------
# Cart and reservations
# ---------------------------------------------------------------------------


class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=1, le=99)
    selected: bool | None = None


class CartSyncIn(BaseModel):
    items: list[CartItemCreate] = Field(default_factory=list)


class CartItemOut(ORMModel):
    id: int
    product_id: int
    quantity: int
    selected: bool
    product: ProductOut
    line_total: float


class CartOut(BaseModel):
    items: list[CartItemOut]
    count: int
    subtotal: float
    selected_subtotal: float


class ReservationCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)
    duration_minutes: int = Field(default=15, ge=1, le=60)


class ReservationOut(ORMModel):
    id: int
    token: str
    product_id: int
    quantity: int
    status: str
    expires_at: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Checkout, parent orders, seller orders, payments
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    address: AddressIn
    payment_method: str = Field(default="sandbox", max_length=60)
    shipping_method: str = Field(default="standard", max_length=60)
    notes: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=120)
    reservation_tokens: list[str] = Field(default_factory=list)
    items: list[CartItemCreate] | None = None


class SellerOrderOut(ORMModel):
    id: int
    seller_order_number: str
    seller_name: str
    status: SellerOrderState
    subtotal: float
    shipping: float
    total: float
    items: list["OrderItemOut"]
    created_at: datetime


class OrderItemOut(ORMModel):
    id: int
    product_id: int | None = None
    product_slug: str | None = None
    name: str
    image: str | None = None
    unit_price: float
    quantity: int
    line_total: float


class OrderOut(ORMModel):
    id: int
    order_number: str
    status: str
    currency: str
    subtotal: float
    shipping: float
    tax: float
    total: float
    customer_name: str
    customer_email: EmailStr
    shipping_address: dict[str, Any]
    payment_method: str
    payment_status: str | None = None
    items: list[OrderItemOut]
    seller_orders: list[SellerOrderOut]
    placed_at: datetime


class OrderList(BaseModel):
    items: list[OrderOut]
    total: int


class PaymentOut(ORMModel):
    id: int
    order_id: int
    idempotency_key: str
    provider: str
    status: str
    amount: float
    currency: str
    created_at: datetime
    verified_at: datetime | None


# ---------------------------------------------------------------------------
# Stores, seller applications, admin
# ---------------------------------------------------------------------------


class StoreIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    story: str = Field(default="", max_length=4000)
    craft: str = Field(default="Textiles", max_length=120)
    location: str | None = Field(default=None, max_length=120)


class StoreOut(ORMModel):
    id: int
    user_id: int
    name: str
    story: str
    craft: str
    location: str | None
    state: str
    notes: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    created_at: datetime


class StoreDecisionIn(BaseModel):
    decision: Literal["Approved", "Changes Requested", "Suspended"]
    reason: str = Field(min_length=2, max_length=1000)


class SellerApplicationCreate(BaseModel):
    studio_name: str = Field(min_length=2, max_length=160)
    craft: str = Field(default="Textiles", max_length=120)
    story: str = Field(min_length=10, max_length=4000)
    location: str | None = Field(default=None, max_length=120)


class SellerApplicationOut(ORMModel):
    id: int
    user_id: int
    studio_name: str
    craft: str
    story: str
    location: str | None
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None


class SellerApplicationList(BaseModel):
    items: list[SellerApplicationOut]
    total: int


class AdminStats(BaseModel):
    users: int
    products: int
    published_products: int
    orders: int
    revenue: float
    pending_stores: int
    pending_reports: int


class AuditLogOut(ORMModel):
    id: int
    actor_id: int | None
    action: str
    target_type: str | None
    target_id: str | None
    reason: str | None
    extra: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="extra",
        serialization_alias="metadata",
    )
    created_at: datetime


class AuditLogList(BaseModel):
    items: list[AuditLogOut]
    total: int


# ---------------------------------------------------------------------------
# Reviews and reports
# ---------------------------------------------------------------------------


class ReviewCreate(BaseModel):
    order_item_id: int
    rating: int = Field(ge=1, le=5)
    message: str = Field(min_length=1, max_length=300)


class ReviewOut(ORMModel):
    id: int
    user_id: int
    product_id: int
    order_item_id: int
    rating: int
    message: str
    author: str
    status: str
    created_at: datetime


class ReviewList(BaseModel):
    items: list[ReviewOut]
    total: int
    average: float


class ReviewReportCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ReviewReportOut(ORMModel):
    id: int
    review_id: int
    reporter_id: int
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class ReviewReportList(BaseModel):
    items: list[ReviewReportOut]
    total: int


# ---------------------------------------------------------------------------
# Recommendations and newsletter
# ---------------------------------------------------------------------------


class RecommendationEventIn(BaseModel):
    product_id: int
    event_id: str | None = Field(default=None, max_length=80)
    event_type: Literal[
        "PRODUCT_VIEW",
        "FAVORITE_ADD",
        "FAVORITE_REMOVE",
        "CART_ADD",
        "CART_REMOVE",
        "RECOMMENDATION_IMPRESSION",
        "RECOMMENDATION_CLICK",
        "DISMISS",
    ] = "PRODUCT_VIEW"
    weight: float = Field(default=1.0, ge=0, le=10)
    occurred_at: datetime | None = None
    session_id: str | None = Field(default=None, max_length=120)
    source_context: str | None = Field(default=None, max_length=120)
    recommendation_request_id: str | None = Field(default=None, max_length=120)
    model_version: str | None = Field(default=None, max_length=80)
    position: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        aliases = {
            "view": "PRODUCT_VIEW",
            "favorite": "FAVORITE_ADD",
            "cart": "CART_ADD",
            "impression": "RECOMMENDATION_IMPRESSION",
            "click": "RECOMMENDATION_CLICK",
            "dismiss": "DISMISS",
        }
        return aliases.get(value.lower(), value.upper())


class RecommendationOut(ORMModel):
    id: int
    slug: str
    name: str
    image: str | None
    price: float
    category: str
    artisan: str
    score: float
    reason: str


class RecommendationList(BaseModel):
    items: list[RecommendationOut]


class RecommendationSnapshotOut(ORMModel):
    snapshot_id: str
    created_at: datetime
    watermark: datetime | None
    taxonomy_version: str
    criteria: dict[str, Any]
    included_count: int
    excluded_count: int
    exclusion_reasons: dict[str, int]


class NewsletterIn(BaseModel):
    email: EmailStr


SellerOrderOut.model_rebuild()
OrderOut.model_rebuild()
