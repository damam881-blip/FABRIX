"""Idempotent development seed data for the FABRIX backend."""
from __future__ import annotations

import os
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import OrderItem, Product, SellerApplication, SellerOrder, Store, User
from .security import hash_password
from .utils import slugify, utcnow
from .utils import money_to_cents

INFERRED = {
    1: ("Metal", "Modern", "Silver"),
    2: ("Natural fiber", "Rustic", "Beige"),
    3: ("Natural fiber", "Minimal", "Gray"),
    4: ("Natural fiber", "Rustic", "Beige"),
    5: ("Clay", "Minimal", "Gray"),
    6: ("Wood", "Rustic", "Brown"),
    7: ("Clay", "Minimal", "Beige"),
    8: ("Metal", "Modern", "Silver"),
    9: ("Natural fiber", "Rustic", "Beige"),
    10: ("Wood", "Rustic", "Brown"),
    11: ("Clay", "Minimal", "Gray"),
    12: ("Natural fiber", "Minimal", "White"),
}

CATALOG = [
    (1, "Sculpted arch earrings", "Aster Metalworks", 46, "Jewelry", "Low stock", 3),
    (2, "Ribbed beeswax candle", "Kindred Flame", 32, "Home objects", "New", 16),
    (3, "Hand-knit pebble scarf", "North Loop Knits", 64, "Fiber & textile", "Natural fibers", 10),
    (4, "Botanical linen hoop", "Field Note Stitchery", 52, "Fiber & textile", "Made to order", 8),
    (5, "Cloudline ceramic vase", "Morrow Clay Studio", 78, "Ceramics", "Bestseller", 9),
    (6, "Woven ember wall piece", "Thread & Timber", 124, "Home objects", "One of a kind", 1),
    (7, "Hand-thrown cup set", "Morrow Clay Studio", 58, "Ceramics", "New", 8),
    (8, "Hammered silver pendant", "Aster Metalworks", 42, "Jewelry", "Small batch", 4),
    (9, "Loom-woven cotton runner", "North Loop Knits", 88, "Fiber & textile", "Natural fibers", 5),
    (10, "Carved oak bookend", "Thread & Timber", 72, "Home objects", "One of a kind", 1),
    (11, "Speckled stoneware bowl", "Morrow Clay Studio", 54, "Ceramics", "Bestseller", 11),
    (12, "Soft linen table cloth", "Field Note Stitchery", 95, "Fiber & textile", "Made by hand", 7),
]

EXTRA_PRODUCT_DATA = {
    1: {
        "description": "Hand-shaped silver arch earrings with an organic, sculptural outline.",
        "details": {"Dimensions": "Approx. 4 × 2 cm"},
    },
    2: {
        "description": "A softly scented beeswax candle poured by hand in small batches.",
        "details": {"Dimensions": "Approx. 10 × 6 cm"},
    },
    3: {
        "description": "A hand-knit scarf in a soft natural-fiber blend, made for everyday warmth.",
        "details": {"Dimensions": "Approx. 175 × 28 cm"},
    },
    4: {
        "description": "Botanical linen hoop embroidery, stitched by hand in a small studio.",
        "details": {"Dimensions": "Approx. 20 cm"},
    },
    5: {
        "description": "A softly sculpted stoneware vase, wheel-thrown and finished by hand. Its cloud-white glaze breaks gently over the natural texture, making every piece subtly different.",
        "details": {"Dimensions": "18 × 12 cm", "Origin": "Portland, OR", "Maker": "Mira Chen"},
    },
    6: {
        "description": "A one-of-a-kind woven wall piece combining wood and fiber in warm ember tones.",
        "details": {"Dimensions": "Approx. 35 × 45 cm"},
    },
}

CURATED_FEATURED = {5, 6, 1, 2, 3, 4}


def _seed_users(db: Session) -> None:
    if os.getenv("FABRIX_SEED_DEMO_USERS", "1") != "1":
        return
    now = utcnow()
    accounts = [
        ("buyer@example.com", "Demo12345", "FABRIX Buyer", "customer", None, False),
        ("artisan@example.com", "Demo12345", "Nora Ellis", "artisan", "North Loop Knits", True),
        ("admin@example.com", "Admin12345", "FABRIX Admin", "admin", None, False),
    ]
    for email, password, name, role, studio, can_sell in accounts:
        if db.scalar(select(User).where(User.email == email)):
            continue
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=name,
            role=role,
            can_shop=True,
            can_sell=can_sell,
            studio_name=studio,
            studio_story="Textile studio focused on slow, considered knitting and weaving." if studio else None,
        )
        db.add(user)
        db.flush()
        if studio:
            db.add(
                Store(
                    user_id=user.id,
                    name=studio,
                    story=user.studio_story or "",
                    craft="Textiles",
                    state="Approved",
                    notes="Seeded artisan studio.",
                    submitted_at=now,
                    approved_at=now,
                )
            )
            db.add(
                SellerApplication(
                    user_id=user.id,
                    studio_name=studio,
                    craft="Textiles",
                    story=user.studio_story or "",
                    status="approved",
                    reviewed_at=now,
                )
            )


def _seed_products(db: Session) -> None:
    makers = sorted({row[2] for row in CATALOG})
    owners: dict[str, User] = {}
    for maker in makers:
        owner = db.scalar(select(User).where(User.studio_name == maker))
        if owner is None:
            email = f"catalog-{slugify(maker)}@seed.invalid"
            owner = db.scalar(select(User).where(User.email == email))
        if owner is None:
            owner = User(
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                full_name=f"{maker} catalog owner",
                role="artisan",
                can_shop=True,
                can_sell=True,
                studio_name=maker,
                studio_story=f"Catalog store for {maker}.",
            )
            db.add(owner)
            db.flush()
        owner.can_sell = True
        owners[maker] = owner
        store = db.scalar(select(Store).where(Store.user_id == owner.id))
        if store is None:
            db.add(
                Store(
                    user_id=owner.id,
                    name=maker,
                    story=owner.studio_story or "",
                    craft="Textiles" if "Knits" in maker or "Stitchery" in maker else "Handmade",
                    state="Approved",
                    notes="Seeded catalog store.",
                    submitted_at=utcnow(),
                    approved_at=utcnow(),
                )
            )
    db.flush()

    studio_owner = owners.get("North Loop Knits")
    if db.scalar(select(Product.id).limit(1)):
        for maker, owner in owners.items():
            db.query(Product).filter(Product.artisan == maker).update(
                {Product.artisan_id: owner.id, Product.studio: maker},
                synchronize_session=False,
            )
        return
    for product_id, name, maker, price, category, tag, stock in CATALOG:
        material, style, color = INFERRED.get(product_id, (None, None, None))
        extra = dict(EXTRA_PRODUCT_DATA.get(product_id, {}))
        owner = owners[maker]
        db.add(
            Product(
                id=product_id,
                artisan_id=owner.id if owner else None,
                slug=slugify(name),
                name=name,
                artisan=maker,
                studio=maker,
                category=category,
                price=float(price),
                image=f"/assets/photos/products/product-{product_id:02d}.jpg",
                images=[f"/assets/photos/products/product-{product_id:02d}.jpg"],
                description=extra.get("description"),
                details=extra.get("details", {}),
                material=material,
                style=style,
                color=color,
                tag=tag,
                materials=[material] if material else [],
                tags=[tag, "Handmade"] if tag else ["Handmade"],
                stock=stock,
                rating=4.9,
                reviews_count=0,
                featured=product_id in CURATED_FEATURED,
                status="Published",
            )
        )


def seed_database() -> None:
    init_db()
    db = SessionLocal()
    try:
        _seed_users(db)
        _seed_products(db)
        for seller_order in db.scalars(select(SellerOrder)).all():
            if seller_order.seller_user_id is not None:
                continue
            item = db.scalar(
                select(OrderItem).where(OrderItem.seller_order_id == seller_order.id)
            )
            if item and item.product_id:
                product = db.get(Product, item.product_id)
                if product and product.artisan_id:
                    seller_order.seller_user_id = product.artisan_id
        for product in db.scalars(select(Product)).all():
            product.price_cents = money_to_cents(product.price)
            product.compare_at_price_cents = (
                money_to_cents(product.compare_at_price)
                if product.compare_at_price is not None
                else None
            )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
    print("FABRIX development data seeded.")
