"""Product catalog, seller listings, moderation, and image uploads."""
from __future__ import annotations

import secrets
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from ..config import ROOT
from ..db import get_db
from ..deps import CurrentUser, DbSession, has_active_store, require_seller
from ..models import Product, Store, UploadAsset, User
from ..schemas import Message, ProductCreate, ProductList, ProductOut, ProductUpdate
from ..services import (
    audit,
    cleanup_upload_orphans,
    notify,
    product_is_eligible,
    upload_paths_for_references,
)
from ..utils import money_to_cents, slugify

router = APIRouter(prefix="/products", tags=["products"])

CURATED_ORDER = [5, 6, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12]
UPLOAD_DIR = ROOT / "assets" / "uploads" / "products"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _image_signature(content: bytes, content_type: str | None) -> bool:
    if content_type in {"image/jpeg", "image/jpg"}:
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def _unique_slug(db: DbSession, base: str, exclude_id: int | None = None) -> str:
    candidate = slugify(base)
    while True:
        query = select(Product.id).where(Product.slug == candidate)
        if exclude_id is not None:
            query = query.where(Product.id != exclude_id)
        if db.scalar(query) is None:
            return candidate
        candidate = f"{slugify(base)}-{secrets.token_hex(2)}"


def _get_product(db: DbSession, identifier: str | int) -> Product:
    if str(identifier).isdigit():
        product = db.get(Product, int(identifier))
    else:
        product = db.scalar(select(Product).where(Product.slug == identifier))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def _can_manage(user, product: Product) -> bool:
    return user.role == "admin" or (
        has_active_store(user) and product.artisan_id == user.id
    )


@router.get("", response_model=ProductList)
def list_products(
    db: DbSession,
    q: str | None = None,
    category: str | None = None,
    artisan: str | None = None,
    tag: str | None = None,
    material: str | None = None,
    style: str | None = None,
    color: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    featured: bool | None = None,
    in_stock: bool | None = None,
    sort: str = "curated",
    page: int = 1,
    page_size: int = 24,
) -> ProductList:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    query = (
        select(Product)
        .join(Store, Store.user_id == Product.artisan_id)
        .join(User, User.id == Product.artisan_id)
        .where(
            Product.status == "Published",
            Store.state == "Approved",
            User.is_active.is_(True),
            User.can_sell.is_(True),
            Product.stock > Product.reserved_stock,
        )
    )

    if q:
        needle = f"%{q}%"
        query = query.where(
            or_(
                Product.name.ilike(needle),
                Product.artisan.ilike(needle),
                Product.studio.ilike(needle),
                Product.category.ilike(needle),
                Product.description.ilike(needle),
                Product.material.ilike(needle),
                Product.style.ilike(needle),
                Product.color.ilike(needle),
                cast(Product.tags, String).ilike(needle),
            )
        )
    for field, value in (
        ("category", category),
        ("material", material),
        ("style", style),
        ("color", color),
    ):
        if value:
            query = query.where(getattr(Product, field).ilike(value))
    if artisan:
        query = query.where(or_(Product.artisan.ilike(f"%{artisan}%"), Product.studio.ilike(f"%{artisan}%")))
    if tag:
        query = query.where(cast(Product.tags, String).ilike(f"%{tag}%"))
    if min_price is not None:
        query = query.where(Product.price_cents >= money_to_cents(min_price))
    if max_price is not None:
        query = query.where(Product.price_cents <= money_to_cents(max_price))
    if featured is not None:
        query = query.where(Product.featured.is_(featured))
    if in_stock is not None:
        query = query.where((Product.stock > Product.reserved_stock) if in_stock else (Product.stock <= Product.reserved_stock))

    if sort == "price-asc":
        query = query.order_by(Product.price_cents.asc(), Product.id.asc())
    elif sort == "price-desc":
        query = query.order_by(Product.price_cents.desc(), Product.id.asc())
    elif sort == "rating":
        query = query.order_by(Product.rating.desc(), Product.reviews_count.desc(), Product.id.asc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc(), Product.id.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc(), Product.id.asc())
    else:
        query = query.order_by(
            case(
                {product_id: index for index, product_id in enumerate(CURATED_ORDER)},
                value=Product.id,
                else_=len(CURATED_ORDER),
            ),
            Product.name.asc(),
            Product.id.asc(),
        )

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    start = (page - 1) * page_size
    window = list(db.scalars(query.offset(start).limit(page_size)).all())
    categories = list(
        db.scalars(
            select(Product.category)
            .join(Store, Store.user_id == Product.artisan_id)
            .join(User, User.id == Product.artisan_id)
            .where(
                Product.status == "Published",
                Store.state == "Approved",
                User.is_active.is_(True),
                User.can_sell.is_(True),
            )
            .distinct()
            .order_by(Product.category)
        ).all()
    )
    return ProductList(
        items=[ProductOut.model_validate(p) for p in window],
        total=total,
        page=page,
        page_size=page_size,
        categories=categories,
    )


@router.get("/featured", response_model=list[ProductOut])
def featured_products(db: DbSession, limit: int = 8) -> list[ProductOut]:
    products = list(
        db.scalars(
            select(Product)
            .join(Store, Store.user_id == Product.artisan_id)
            .where(
                Product.status == "Published",
                Product.featured.is_(True),
                Store.state == "Approved",
            )
            .order_by(Product.rating.desc())
            .limit(min(max(limit, 1), 24))
        ).all()
    )
    return [ProductOut.model_validate(p) for p in products]


@router.get("/mine", response_model=list[ProductOut])
def my_listings(user: CurrentUser, db: DbSession, _=Depends(require_seller)) -> list[ProductOut]:
    rows = db.scalars(
        select(Product).where(Product.artisan_id == user.id).order_by(Product.created_at.desc())
    ).all()
    return [ProductOut.model_validate(row) for row in rows]


@router.get("/{identifier}", response_model=ProductOut)
def get_product(identifier: str, db: DbSession) -> ProductOut:
    product = _get_product(db, identifier)
    if not product_is_eligible(db, product):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductOut.model_validate(product)


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_seller)],
)
def create_product(payload: ProductCreate, user: CurrentUser, db: DbSession) -> ProductOut:
    raw = payload.model_dump(exclude={"slug"})
    editable = {
        "name", "category", "price", "compare_at_price", "image", "images",
        "description", "details", "material", "style", "color", "tag",
        "materials", "tags", "stock",
    }
    data = {key: value for key, value in raw.items() if key in editable}
    store = user.store
    if user.role != "admin" and not store:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Create a studio first")
    artisan_name = store.name if store else user.full_name
    if user.role != "admin" and payload.status == "Published":
        if not has_active_store(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Studio is not approved")
    data["artisan"] = artisan_name
    data["studio"] = artisan_name
    data["status"] = "Draft" if user.role != "admin" else payload.status
    data["price_cents"] = money_to_cents(data["price"])
    data["compare_at_price_cents"] = (
        money_to_cents(data["compare_at_price"])
        if data.get("compare_at_price") is not None
        else None
    )
    product = Product(
        **data,
        slug=_unique_slug(db, payload.slug or payload.name),
        artisan_id=user.id if user.role != "admin" else None,
    )
    db.add(product)
    db.flush()
    notify(db, user.id, f"Listing draft created: {product.name}")
    db.commit()
    db.refresh(product)
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, user: CurrentUser, db: DbSession) -> ProductOut:
    product = _get_product(db, product_id)
    if not _can_manage(user, product):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your product")

    requested_status = payload.status
    old_status = product.status
    if requested_status == "Blocked" and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can block listings")
    if requested_status == "Published" and user.role != "admin":
        if not has_active_store(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Studio is not approved")
    if user.role != "admin" and requested_status not in {None, "Draft", "Unpublished", "Published"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can apply that product state",
        )

    protected = {
        "artisan", "studio", "rating", "reviews_count", "featured",
        "status",
    }
    if user.role != "admin":
        attempted = protected.intersection(payload.model_dump(exclude_unset=True))
        unsupported = attempted - {"status"}
        if unsupported:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Protected product fields cannot be changed by sellers",
            )

    allowed = {
        "name", "category", "price", "compare_at_price", "image", "images",
        "description", "details", "material", "style", "color", "tag",
        "materials", "tags", "stock",
    }
    if user.role == "admin":
        allowed |= protected
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field not in allowed:
            continue
        setattr(product, field, value)
    if "price" in payload.model_dump(exclude_unset=True):
        product.price_cents = money_to_cents(product.price)
    if "compare_at_price" in payload.model_dump(exclude_unset=True):
        product.compare_at_price_cents = (
            money_to_cents(product.compare_at_price)
            if product.compare_at_price is not None
            else None
        )
    if requested_status and requested_status != old_status:
        audit(
            db,
            "product.status_change",
            actor_id=user.id,
            target_type="product",
            target_id=product.id,
            metadata={"from": old_status, "to": requested_status},
        )
    db.commit()
    db.refresh(product)
    return ProductOut.model_validate(product)


@router.delete("/{product_id}", response_model=Message)
def delete_product(product_id: int, user: CurrentUser, db: DbSession) -> Message:
    product = _get_product(db, product_id)
    if not _can_manage(user, product):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your product")
    product.status = "Unpublished"
    db.commit()
    return Message(message="Product unpublished")


@router.post("/{product_id}/images", response_model=ProductOut)
async def upload_product_image(
    product_id: int,
    user: CurrentUser,
    db: DbSession,
    replace: bool = False,
    file: UploadFile = File(...),
) -> ProductOut:
    product = _get_product(db, product_id)
    if not _can_manage(user, product):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your product")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image type")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".jpg"
    target_dir = UPLOAD_DIR / str(product.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(8)}{suffix}"
    target = target_dir / filename

    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large")
    if not _image_signature(content, file.content_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image content")
    target.write_bytes(content)

    url = f"/assets/uploads/products/{product.id}/{filename}"
    previous_images = list(product.images or [])
    obsolete_paths = (
        upload_paths_for_references(db, UPLOAD_DIR, [previous_images, product.image])
        if replace
        else []
    )
    images = [] if replace else previous_images
    images.append(url)
    product.images = images
    if replace or not product.image:
        product.image = url
    db.add(
        UploadAsset(
            product_id=product.id,
            path=str(target.resolve()),
            content_type=file.content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    )
    audit(
        db,
        "upload.created",
        actor_id=user.id,
        target_type="product",
        target_id=product.id,
        metadata={"path": url, "size_bytes": len(content)},
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload could not be committed",
        ) from exc
    if obsolete_paths:
        cleanup_upload_orphans(
            db, UPLOAD_DIR, user.id, dry_run=False, only_paths=obsolete_paths
        )
    db.refresh(product)
    return ProductOut.model_validate(product)
