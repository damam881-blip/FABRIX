# FABRIX Database and Migration Report

## Current engine

The default database is SQLite at `data/fabrix.db`. SQLAlchemy is used as the
database abstraction. SQLite foreign keys are now enabled for every SQLAlchemy
connection.

## Migration bridge

The original application used `Base.metadata.create_all()` without a
migration history. A dependency-free migration bridge was added in
`backend/db.py` to safely migrate the current local database before a full
versioned migration framework is introduced.

Current migration records include:

- `payments_idempotency_v1`
- `sqlite_foreign_keys_v1`
- `recommendation_event_context_v1`

The bridge:

- Creates `schema_migrations`.
- Adds payment ownership, operation, and request-hash fields.
- Backfills payment ownership from parent orders.
- Replaces the global payment-key index with a user/operation/key index.
- Backfills seller-order ownership from purchased products.
- Adds recommendation event provenance fields.

The active database was backed up before migration and passed SQLite integrity
checking.

## Authoritative relationships

- Users own addresses, carts, favorites, reservations, reviews, and stores.
- Stores belong one-to-one to users.
- Products have an authoritative `artisan_id`.
- Seller orders have an authoritative `seller_user_id`.
- Order items belong to both a parent order and seller order.
- Payments belong one-to-one to parent orders and are scoped to the checkout
  user and operation.
- Reviews are unique per order item.
- Recommendation events have unique event IDs.

## Remaining database work

- Adopt a full versioned migration tool for production deployment.
- Convert money fields from floating-point to fixed-precision numeric types.
- Add database-level state/value constraints through migrations.
- Add composite consistency constraints for order, seller-order, and item
  relationships where supported by the target database.
- Add upload metadata ownership records.
- Add data-retention and recommendation-event deletion structures.
