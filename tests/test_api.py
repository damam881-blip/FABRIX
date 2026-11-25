"""End-to-end smoke tests for the FABRIX backend."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

DB_PATH = Path(tempfile.gettempdir()) / "fabrix_test_api.db"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["FABRIX_DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["FABRIX_SECRET_KEY"] = "test-secret-key"
os.environ["FABRIX_SEED_DEMO_USERS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

ADDRESS = {
    "full_name": "Test Buyer",
    "email": "buyer@example.com",
    "phone": "555-0100",
    "line1": "12 Test Street",
    "city": "Portland",
    "region": "OR",
    "postal_code": "97201",
    "country": "US",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def token_for(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_catalog(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"
    products = client.get("/api/v1/products").json()
    assert products["total"] == 12
    assert [p["id"] for p in products["items"][:3]] == [5, 6, 1]


def test_catalog_filters_are_bounded_and_database_backed(client: TestClient):
    from sqlalchemy import event
    from backend.db import engine

    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            "/api/v1/products",
            params={
                "q": "scarf",
                "category": "Textiles",
                "min_price": 10,
                "max_price": 100,
                "in_stock": "true",
                "page": 1,
                "page_size": 2,
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 2
    assert payload["total"] >= len(payload["items"])
    assert len(statements) <= 4
    assert any("products" in statement.lower() and "where" in statement.lower() for statement in statements)


def test_seed_accounts_login(client: TestClient):
    buyer = token_for(client, "buyer@example.com", "Demo12345")
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    admin = token_for(client, "admin@example.com", "Admin12345")
    assert buyer and artisan and admin


def test_register_and_cart_requires_auth(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newbuyer@example.com",
            "password": "Password123",
            "full_name": "New Buyer",
            "role": "customer",
        },
    )
    assert response.status_code == 201
    assert client.get("/api/v1/cart").status_code == 401
    token = response.json()["access_token"]
    assert client.get("/api/v1/cart", headers=auth(token)).status_code == 200


def test_favorites_and_cart(client: TestClient):
    token = token_for(client, "buyer@example.com", "Demo12345")
    toggled = client.post("/api/v1/favorites/toggle/3", headers=auth(token))
    assert toggled.status_code == 200
    assert 3 in toggled.json()["ids"]
    cart = client.post(
        "/api/v1/cart/add", headers=auth(token), json={"product_id": 3, "quantity": 2}
    )
    assert cart.status_code == 200
    assert cart.json()["count"] == 2


def test_checkout_fulfillment_review_and_idempotency(client: TestClient):
    buyer = token_for(client, "buyer@example.com", "Demo12345")
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    admin = token_for(client, "admin@example.com", "Admin12345")

    client.post("/api/v1/cart/add", headers=auth(buyer), json={"product_id": 3, "quantity": 2})
    reservation = client.post(
        "/api/v1/reservations",
        headers=auth(buyer),
        json={"product_id": 3, "quantity": 1},
    )
    assert reservation.status_code == 201

    payload = {
        "address": ADDRESS,
        "payment_method": "sandbox",
        "idempotency_key": "test-checkout-001",
        "reservation_tokens": [reservation.json()["token"]],
    }
    first = client.post("/api/v1/orders/checkout", headers=auth(buyer), json=payload)
    assert first.status_code == 201, first.text
    order = first.json()
    assert order["total"] > 0
    assert len(order["seller_orders"]) >= 1

    retry = client.post("/api/v1/orders/checkout", headers=auth(buyer), json=payload)
    assert retry.json()["order_number"] == order["order_number"]

    child = next(
        child for child in order["seller_orders"] if child["seller_name"] == "North Loop Knits"
    )
    item = next(item for item in order["items"] if item["name"] == "Hand-knit pebble scarf")

    blocked = client.post(
        "/api/v1/reviews",
        headers=auth(buyer),
        json={"order_item_id": item["id"], "rating": 5, "message": "Lovely scarf"},
    )
    assert blocked.status_code == 400

    assert (
        client.patch(
            f"/api/v1/orders/seller/{child['seller_order_number']}/status?next_status=Processing",
            headers=auth(artisan),
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/orders/seller/{child['seller_order_number']}/status?next_status=Shipped",
            headers=auth(artisan),
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/orders/seller/{child['seller_order_number']}/status?next_status=Delivered",
            headers=auth(admin),
        ).status_code
        == 200
    )

    review = client.post(
        "/api/v1/reviews",
        headers=auth(buyer),
        json={"order_item_id": item["id"], "rating": 5, "message": "Lovely scarf"},
    )
    assert review.status_code == 201, review.text
    reviews = client.get("/api/v1/reviews/product/3").json()
    assert reviews["total"] >= 1
    assert reviews["average"] == 5.0


def test_store_lifecycle_and_admin_stats(client: TestClient):
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "maker@example.com",
            "password": "Password123",
            "full_name": "New Maker",
            "role": "customer",
        },
    )
    token = registered.json()["access_token"]
    created = client.post(
        "/api/v1/seller/store",
        headers=auth(token),
        json={"name": "Maker Studio", "story": "A small textile studio."},
    )
    assert created.status_code == 201, created.text
    submitted = client.post("/api/v1/seller/store/submit", headers=auth(token))
    assert submitted.json()["state"] == "Pending"

    admin = token_for(client, "admin@example.com", "Admin12345")
    store_id = created.json()["id"]
    approved = client.patch(
        f"/api/v1/admin/stores/{store_id}",
        headers=auth(admin),
        json={"decision": "Approved", "reason": "Story verified"},
    )
    assert approved.status_code == 200, approved.text
    stats = client.get("/api/v1/admin/stats", headers=auth(admin)).json()
    assert stats["users"] >= 4
    assert stats["pending_stores"] == 0


def test_recommendations_respect_events(client: TestClient):
    token = token_for(client, "buyer@example.com", "Demo12345")
    event = client.post(
        "/api/v1/recommendations/events",
        headers=auth(token),
        json={"product_id": 3, "event_id": "test-event-001", "event_type": "favorite"},
    )
    assert event.status_code == 201
    repeat = client.post(
        "/api/v1/recommendations/events",
        headers=auth(token),
        json={"product_id": 3, "event_id": "test-event-001", "event_type": "favorite"},
    )
    assert repeat.status_code == 201
    conflict = client.post(
        "/api/v1/recommendations/events",
        headers=auth(token),
        json={"product_id": 2, "event_id": "test-event-001", "event_type": "view"},
    )
    assert conflict.status_code == 409
    items = client.get("/api/v1/recommendations?limit=3", headers=auth(token)).json()["items"]
    assert len(items) == 3
    assert all(item["score"] >= 0 for item in items)


def test_public_registration_cannot_create_admin(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-admin@example.com",
            "password": "Password123",
            "full_name": "Not Admin",
            "role": "admin",
        },
    )
    assert response.status_code == 422
    assert client.post("/api/v1/auth/logout").status_code == 401
    long_utf8_password = "é" * 40
    assert client.post(
        "/api/v1/auth/register",
        json={
            "email": "too-long-utf8@example.com",
            "password": long_utf8_password,
            "full_name": "UTF8 Password",
            "role": "customer",
        },
    ).status_code == 422


def test_login_bruteforce_throttling(client: TestClient):
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "bruteforce@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "bruteforce@example.com", "password": "wrong-password"},
    )
    assert limited.status_code == 429


def test_checkout_idempotency_is_user_scoped_and_payload_bound(client: TestClient):
    buyer = token_for(client, "buyer@example.com", "Demo12345")
    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": "idempotency-other@example.com",
            "password": "Password123",
            "full_name": "Other Buyer",
            "role": "customer",
        },
    ).json()["access_token"]
    payload = {
        "address": ADDRESS,
        "items": [{"product_id": 2, "quantity": 1}],
        "idempotency_key": "scoped-idempotency-key",
    }
    first = client.post("/api/v1/orders/checkout", headers=auth(buyer), json=payload)
    assert first.status_code == 201, first.text
    other_payload = dict(payload)
    other_payload["address"] = {**ADDRESS, "email": "idempotency-other@example.com"}
    second = client.post("/api/v1/orders/checkout", headers=auth(other), json=other_payload)
    assert second.status_code == 201, second.text
    assert second.json()["order_number"] != first.json()["order_number"]
    assert second.json()["customer_email"] == "idempotency-other@example.com"

    changed = dict(payload)
    changed["items"] = [{"product_id": 2, "quantity": 2}]
    conflict = client.post("/api/v1/orders/checkout", headers=auth(buyer), json=changed)
    assert conflict.status_code == 409


def test_seller_cannot_manipulate_protected_product_metadata(client: TestClient):
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    response = client.patch(
        "/api/v1/products/3",
        headers=auth(artisan),
        json={"featured": True, "rating": 1, "reviews_count": 999},
    )
    assert response.status_code == 403


def test_recommendation_purchase_events_are_server_only(client: TestClient):
    token = token_for(client, "buyer@example.com", "Demo12345")
    response = client.post(
        "/api/v1/recommendations/events",
        headers=auth(token),
        json={"product_id": 2, "event_type": "PURCHASE"},
    )
    assert response.status_code == 422


def test_artisan_cannot_review_own_product(client: TestClient):
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    admin = token_for(client, "admin@example.com", "Admin12345")
    payload = {
        "address": {
            **ADDRESS,
            "full_name": "Nora Ellis",
            "email": "artisan@example.com",
        },
        "items": [{"product_id": 3, "quantity": 1}],
        "idempotency_key": "artisan-self-review-order",
    }
    order = client.post(
        "/api/v1/orders/checkout", headers=auth(artisan), json=payload
    )
    assert order.status_code == 201, order.text
    child = order.json()["seller_orders"][0]["seller_order_number"]
    assert client.patch(
        f"/api/v1/orders/seller/{child}/status?next_status=Processing",
        headers=auth(artisan),
    ).status_code == 200
    assert client.patch(
        f"/api/v1/orders/seller/{child}/status?next_status=Shipped",
        headers=auth(artisan),
    ).status_code == 200
    assert client.patch(
        f"/api/v1/orders/seller/{child}/status?next_status=Delivered",
        headers=auth(admin),
    ).status_code == 200
    item_id = order.json()["items"][0]["id"]
    review = client.post(
        "/api/v1/reviews",
        headers=auth(artisan),
        json={"order_item_id": item_id, "rating": 5, "message": "Self review"},
    )
    assert review.status_code == 403


def test_suspended_store_products_are_not_purchasable(client: TestClient):
    admin = token_for(client, "admin@example.com", "Admin12345")
    buyer = token_for(client, "buyer@example.com", "Demo12345")
    stores = client.get("/api/v1/admin/stores", headers=auth(admin)).json()
    north_loop = next(store for store in stores if store["name"] == "North Loop Knits")
    suspended = client.patch(
        f"/api/v1/admin/stores/{north_loop['id']}",
        headers=auth(admin),
        json={"decision": "Suspended", "reason": "Security regression test"},
    )
    assert suspended.status_code == 200, suspended.text
    assert client.post(
        "/api/v1/cart/add",
        headers=auth(buyer),
        json={"product_id": 3, "quantity": 1},
    ).status_code == 404
    assert all(
        item["id"] != 3
        for item in client.get("/api/v1/recommendations", headers=auth(buyer)).json()["items"]
    )
    assert client.get("/api/v1/products/mine", headers=auth(token_for(client, "artisan@example.com", "Demo12345"))).status_code == 403
    assert client.get("/api/v1/orders/seller/orders", headers=auth(token_for(client, "artisan@example.com", "Demo12345"))).status_code == 403
    restored = client.patch(
        f"/api/v1/admin/stores/{north_loop['id']}",
        headers=auth(admin),
        json={"decision": "Approved", "reason": "Restore seeded verification state"},
    )
    assert restored.status_code == 200


def test_cart_sync_and_favorites_require_current_product_eligibility(client: TestClient):
    from backend.db import SessionLocal
    from backend.models import Product

    db = SessionLocal()
    product = db.get(Product, 3)
    original_status = product.status
    product.status = "Unpublished"
    db.commit()
    db.close()
    buyer = token_for(client, "buyer@example.com", "Demo12345")
    try:
        sync = client.post(
            "/api/v1/cart/sync",
            headers=auth(buyer),
            json={"items": [{"product_id": 3, "quantity": 1}]},
        )
        assert sync.status_code == 200
        assert all(item["product_id"] != 3 for item in sync.json()["items"])
        assert client.post("/api/v1/favorites/3", headers=auth(buyer)).status_code == 404
    finally:
        db = SessionLocal()
        db.get(Product, 3).status = original_status
        db.commit()
        db.close()


def test_recommendation_events_respect_consent_and_attribution(client: TestClient):
    from backend.db import SessionLocal
    from backend.models import RecommendationEvent, User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "buyer@example.com").one()
        user.consent = False
        db.commit()
    finally:
        db.close()

    buyer = token_for(client, "buyer@example.com", "Demo12345")
    no_consent = client.post(
        "/api/v1/recommendations/events",
        headers=auth(buyer),
        json={"product_id": 2, "event_id": "no-consent-event", "event_type": "favorite"},
    )
    assert no_consent.status_code == 201
    assert "not recorded" in no_consent.json()["message"]

    anonymous_favorite = client.post(
        "/api/v1/recommendations/events",
        json={"product_id": 2, "event_type": "favorite"},
    )
    assert anonymous_favorite.status_code == 401

    db = SessionLocal()
    try:
        assert db.query(RecommendationEvent).filter(
            RecommendationEvent.event_id == "no-consent-event"
        ).count() == 0
    finally:
        db.close()


def test_impression_acknowledgment_and_privacy_controls(client: TestClient):
    impression = client.post(
        "/api/v1/recommendations/events",
        json={
            "product_id": 2,
            "event_id": "impression-ack-001",
            "event_type": "impression",
            "recommendation_request_id": "req-001",
            "position": 2,
        },
    )
    assert impression.status_code == 201
    duplicate = client.post(
        "/api/v1/recommendations/events",
        json={
            "product_id": 2,
            "event_id": "impression-ack-001",
            "event_type": "impression",
            "recommendation_request_id": "req-001",
            "position": 2,
        },
    )
    assert duplicate.status_code == 201
    missing_context = client.post(
        "/api/v1/recommendations/events",
        json={"product_id": 2, "event_type": "impression"},
    )
    assert missing_context.status_code == 422

    admin = token_for(client, "admin@example.com", "Admin12345")
    snapshot = client.post("/api/v1/admin/recommendations/snapshots", headers=auth(admin))
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["included_count"] >= 1
    cleanup = client.post(
        "/api/v1/admin/recommendations/retention-cleanup?retention_days=90",
        headers=auth(admin),
    )
    assert cleanup.status_code == 200

    buyer = token_for(client, "buyer@example.com", "Demo12345")
    privacy = client.delete("/api/v1/users/me/recommendation-data", headers=auth(buyer))
    assert privacy.status_code == 200


def test_invalid_upload_is_rejected_without_product_mutation(client: TestClient):
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    before_response = client.get("/api/v1/products/3")
    assert before_response.status_code == 200
    before = before_response.json()["images"]
    response = client.post(
        "/api/v1/products/3/images",
        headers=auth(artisan),
        files={"file": ("fake.jpg", b"not-an-image", "image/jpeg")},
    )
    assert response.status_code == 400
    assert client.get("/api/v1/products/3").json()["images"] == before


def test_managed_upload_replacement_removes_only_obsolete_asset(client: TestClient):
    from backend.db import SessionLocal
    from backend.models import UploadAsset

    artisan = token_for(client, "artisan@example.com", "Demo12345")
    png_one = b"\x89PNG\r\n\x1a\n" + b"first"
    png_two = b"\x89PNG\r\n\x1a\n" + b"second"
    first = client.post(
        "/api/v1/products/3/images",
        headers=auth(artisan),
        files={"file": ("one.png", png_one, "image/png")},
    )
    assert first.status_code == 200, first.text
    db = SessionLocal()
    first_asset = db.query(UploadAsset).order_by(UploadAsset.id.desc()).first()
    first_path = first_asset.path
    db.close()
    second = client.post(
        "/api/v1/products/3/images?replace=true",
        headers=auth(artisan),
        files={"file": ("two.png", png_two, "image/png")},
    )
    assert second.status_code == 200, second.text
    db = SessionLocal()
    try:
        assets = db.query(UploadAsset).filter(UploadAsset.product_id == 3).all()
        assert len(assets) == 1
        assert assets[0].path != first_path
    finally:
        db.close()


def test_sqlite_foreign_keys_are_enabled():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from backend.db import engine

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO products(slug, name, artisan, category, price, stock, "
                    "reserved_stock, images, details, materials, tags, status) "
                    "VALUES ('invalid-integrity-test', 'Invalid', 'Test', 'Test', -1, 1, 0, '[]', '{}', '[]', '[]', 'Draft')"
                )
            )
    except IntegrityError:
        pass
    else:
        raise AssertionError("negative product prices must be rejected by SQLite")


def test_sandbox_cancellation_refund_and_inventory_are_idempotent(client: TestClient):
    from backend.db import SessionLocal
    from backend.models import Payment, Product, Refund

    buyer = token_for(client, "buyer@example.com", "Demo12345")
    db = SessionLocal()
    before_stock = db.get(Product, 2).stock
    db.close()
    order_response = client.post(
        "/api/v1/orders/checkout",
        headers=auth(buyer),
        json={
            "address": ADDRESS,
            "items": [{"product_id": 2, "quantity": 1}],
            "idempotency_key": "sandbox-cancel-refund-test",
        },
    )
    assert order_response.status_code == 201, order_response.text
    order = order_response.json()
    child = order["seller_orders"][0]["seller_order_number"]
    db = SessionLocal()
    after_checkout = db.get(Product, 2).stock
    db.close()
    assert after_checkout == before_stock - 1

    cancelled = client.post(
        f"/api/v1/orders/seller/{child}/cancel", headers=auth(buyer)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "Cancelled"
    assert client.post(
        f"/api/v1/orders/seller/{child}/cancel", headers=auth(buyer)
    ).status_code == 400

    db = SessionLocal()
    try:
        assert db.get(Product, 2).stock == before_stock
        payment = db.query(Payment).filter(Payment.order_id == order["id"]).one()
        assert payment.status == "sandbox_refunded"
        assert payment.amount_cents == round(payment.amount * 100)
        assert db.query(Refund).filter(Refund.payment_id == payment.id).count() == 1
    finally:
        db.close()


def test_money_uses_integer_minor_units_and_rejects_fractional_cent(client: TestClient):
    from backend.db import SessionLocal
    from backend.models import Order, Payment, Product
    from backend.seed import seed_database

    seed_database()

    db = SessionLocal()
    try:
        assert all(row.price_cents == round(row.price * 100) for row in db.query(Product).all())
        assert all(row.total_cents == round(row.total * 100) for row in db.query(Order).all())
        assert all(row.amount_cents == round(row.amount * 100) for row in db.query(Payment).all())
    finally:
        db.close()
    artisan = token_for(client, "artisan@example.com", "Demo12345")
    response = client.post(
        "/api/v1/products",
        headers=auth(artisan),
        json={"name": "Fractional Cent", "price": 1.001, "stock": 1},
    )
    assert response.status_code == 422


def test_legacy_float_compatibility_field_is_not_financial_authority():
    from backend.db import SessionLocal
    from backend.models import Product

    db = SessionLocal()
    product = db.get(Product, 2)
    original_price = product.price
    original_cents = product.price_cents
    product.price = original_price + 0.01
    db.commit()
    db.refresh(product)
    assert product.price_cents == original_cents
    product.price = original_price
    db.commit()
    db.close()
