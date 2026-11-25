# FABRIX Recommendation Data Foundation

This document describes the recommendation data foundation that is actually
implemented in this repository. It is a source-code and test-grounded
description, not a product promise. The existing endpoint is a deterministic
baseline recommender; the advanced Recommendation System is still future work.
See `docs/RECOMMENDATION_SYSTEM_HANDOFF.md` for the implementation handoff.

Authoritative source files:

- `backend/schemas.py` — event and response contracts.
- `backend/models.py` — persisted event, snapshot, product, and user fields.
- `backend/routers/recommendations.py` — event ingestion, serving, retention,
  and snapshot endpoints.
- `backend/services.py` — eligibility, retention, and snapshot extraction.
- `backend/routers/orders.py` — trusted purchase-event creation.
- `backend/routers/users.py` — consent updates and user-data deletion.
- `tests/test_api.py` — automated evidence.

## 1. Event taxonomy

The client schema enforces this exact `Literal` taxonomy in
`backend/schemas.py` (`RecommendationEventIn.event_type`):

| Event type | Client may submit | Anonymous allowed | Configured event factor |
|---|---:|---:|---:|
| `PRODUCT_VIEW` | Yes | Yes | `0.5` |
| `FAVORITE_ADD` | Yes | No | `3.0` |
| `FAVORITE_REMOVE` | Yes | No | `1.0` |
| `CART_ADD` | Yes | No | `2.0` |
| `CART_REMOVE` | Yes | No | `1.0` |
| `RECOMMENDATION_IMPRESSION` | Yes | Yes | `1.0` |
| `RECOMMENDATION_CLICK` | Yes | Yes | `1.0` |
| `DISMISS` | Yes | No | `-4.0` (`EVENT_WEIGHTS`) |

The event factors live in `EVENT_WEIGHTS` at
`backend/routers/recommendations.py:21-26`. Types absent from that map use a
factor of `1.0`.

Input aliases are normalized before validation: `view`, `favorite`, `cart`,
`impression`, `click`, and `dismiss` map to the canonical names above; other
values are uppercased and must still match the literal. `PURCHASE` is rejected
with HTTP 422 when submitted by a client. Purchase events are generated only by
checkout in `backend/routers/orders.py`, using `event_type="PURCHASE"` and
`weight=4.0`.

Anonymous callers may submit only `PRODUCT_VIEW`,
`RECOMMENDATION_IMPRESSION`, and `RECOMMENDATION_CLICK`. Private interaction
types require authentication and return HTTP 401 otherwise. An invalid or
expired bearer token is treated as anonymous by `OptionalUser`, not as an
authentication error.

`RECOMMENDATION_IMPRESSION` additionally requires a non-empty
`recommendation_request_id`; otherwise the API returns HTTP 422. This is
API-level impression acknowledgment only. The current frontend does not emit
impression, click, or dismiss events, and the server does not generate a
recommendation request ID.

## 2. Event fields and identity

`RecommendationEventIn` accepts:

- `product_id: int` — required; must resolve to a current, eligible product.
- `event_id: str | None` — optional, maximum 80 characters.
- `event_type` — one of the canonical types above; defaults to `PRODUCT_VIEW`.
- `weight: float` — optional client multiplier, default `1.0`, range `0` to
  `10`. The stored weight is `client weight × EVENT_WEIGHTS[type]`, so the
  resulting stored value can exceed `10`.
- `occurred_at: datetime | None` — optional; no range or future-time validation
  is currently applied.
- `session_id`, `source_context`, `recommendation_request_id` — optional strings
  up to 120 characters.
- `model_version` — optional string up to 80 characters.
- `position: int | None` — optional, range `0` to `10000`.

Server-owned fields are not client-settable:

- `user_id` is taken from the authenticated request context.
- `consent_snapshot` is set to `bool(user and user.consent)`.
- `received_at` is server-generated UTC time.
- Database `id` and `created_at` are managed by the ORM.

`occurred_at` falls back to the server time when absent. The ORM and API use
naive UTC timestamps from `backend/utils.py`.

Event ID behavior:

- If no `event_id` is supplied, the server generates a 24-character hex ID with
  `secrets.token_hex(12)`.
- A duplicate ID with the same `(product_id, user_id, event_type)` is a no-op
  that returns HTTP 201 with `Event already recorded`.
- A reused ID with a different product, user, or event type returns HTTP 409.
- A database uniqueness race is caught and resolved with the same comparison.
- Dedup compares only those three fields. Weight, timestamps, session context,
  request ID, model version, and position are not part of the duplicate key.
  IDs are global across users.

Purchase events from checkout use deterministic IDs of the form
`purchase:{order_number}:{product_id}` and attach to the authenticated buyer.
They are written in the same database transaction as the order and payment
records, so checkout idempotency also prevents duplicate purchase events.

## 3. Consent, privacy, and retention

Implemented behavior:

- **Recording gate:** when an authenticated user has `consent=False`, event
  ingestion returns HTTP 201 but writes no event. The response explicitly says
  the event was not recorded because consent is disabled.
- **Serving gate:** `GET /api/v1/recommendations` reads a user's interaction
  history only when the user is authenticated and `consent=True`. Otherwise it
  returns general discovery results.
- **Opt-out controls:** `PATCH /api/v1/users/me` accepts both `personalization`
  and `consent`; registration accepts both flags. The frontend updates or
  clears both together. Server-side event recording and serving currently
  enforce `consent` only; `personalization` is not independently checked by the
  backend.
- **User-data deletion:** `DELETE /api/v1/users/me/recommendation-data`
  deletes all `RecommendationEvent` rows for the authenticated user, sets both
  `consent` and `personalization` to `False`, writes an audit entry
  `recommendation.privacy_deleted` with the deleted count, and commits.
- **Retention cleanup:** `POST /api/v1/admin/recommendations/retention-cleanup`
  is admin-only. `retention_days` defaults to `90` and must be between `1` and
  `3650`. It deletes events whose `created_at` is older than the cutoff; it
  does not use `received_at` or `occurred_at`. An audit entry
  `recommendation.retention_cleanup` is written only when rows were deleted.
- **Privacy-aware snapshot extraction:** anonymous events are included.
  Authenticated events are included only when the user still exists, is active,
  and has `consent=True`. Excluded rows are counted under
  `consent_or_inactive_user`. The `retention` exclusion reason is currently
  hard-coded to `0`.
- **Audit visibility:** audit rows can be read by an admin through
  `GET /api/v1/admin/audit`. Event recording itself does not create an audit
  row.

Implemented audit actions include `recommendation.privacy_deleted`,
`recommendation.retention_cleanup`, `recommendation.snapshot.created`, and
`order.created` for checkout.

Not implemented yet: role-separated behavioral signals, a privacy-reviewed
training export, and immutability of snapshot source rows after creation.

## 4. Dataset snapshots and lineage

`RecommendationDatasetSnapshot` is implemented in `backend/models.py` with:

- `snapshot_id: str` primary key, generated as `snap_<urlsafe token>`.
- `created_at` timestamp.
- `watermark: datetime | None` — maximum `received_at` across all events when
  the snapshot is created.
- `taxonomy_version: str`, currently the literal `"v1"`.
- `criteria: JSON` — currently `consent_required_for_authenticated_events`,
  `active_users_only`, and `retention_days=90`.
- `included_count`, `excluded_count`, and `exclusion_reasons: JSON`.

Creation happens through `POST /api/v1/admin/recommendations/snapshots`, which
calls `create_recommendation_snapshot` in `backend/services.py`, writes an audit
entry, and returns `RecommendationSnapshotOut`.

Available lineage: a snapshot ID, creation time, source watermark, taxonomy
version, static criteria, included/excluded counts, exclusion reasons, and an
audit association.

Still missing for reproducibility or full model lineage:

- No event-ID manifest, event hashes, or immutable copy of the included rows.
- No GET/list/read endpoint for stored snapshots.
- No train/validation/test export tooling.
- No code/model version hash. Event `model_version` is arbitrary client input
  and is not used by serving, scoring, or snapshot creation.
- No actual retention-based exclusion count; that field is always `0`.
- No `personalization` or product-eligibility criteria recorded in `criteria`.
- Snapshot rows can be made non-reproducible by later user deletion or
  retention cleanup because no frozen event copy is stored.

## 5. Product eligibility

`product_is_eligible` in `backend/services.py` is the shared predicate. A
product is eligible only when all of these hold:

1. `status == "Published"`.
2. `available_stock > 0`, where `available_stock = max(stock - reserved_stock, 0)`.
3. `artisan_id` is not `None`.
4. The referenced owner exists, `is_active`, and `can_sell`.
5. That owner's unique `Store` row exists and has `state == "Approved"`.

Callers of the shared helper:

- `record_event` — rejects events for ineligible products with HTTP 404.
- `recommend` — final filter over candidate products.
- `checkout` — rejects explicit ineligible items with 404 and silently skips
  ineligible cart lines.
- `cart` add, patch, and sync — rejects or drops ineligible products.
- `favorites` add/toggle — rejects ineligible products. `remove_favorite` does
  not re-check eligibility.
- `reservations` — rejects ineligible products.
- `get_product` — returns 404 for ineligible product detail.

Catalog listing and featured-product endpoints use equivalent joins/filters
directly rather than calling the helper.

## 6. Recommendation-relevant catalog foundation

Products persist the attributes a recommendation developer can use:

- Identifier, slug, name, description, and image references.
- `category`, `material`, `style`, `tag`, `materials`, and `tags`.
- `artisan_id` for store ownership.
- `status`, `stock`, `reserved_stock`, and derived `available_stock`.
- `rating`, `reviews_count`, and `featured`.
- Integer minor-unit price columns, with legacy float monetary columns kept
  only for API compatibility.

Product categories, materials, and styles are currently plain string
attributes, not normalized taxonomy tables. There is no normalized tag table,
category hierarchy, or learned product embedding.

## 7. Existing baseline recommendation behavior

`GET /api/v1/recommendations` is an **existing baseline implementation**. A new
developer should extend it, not recreate it.

- Authentication is optional. Guests and invalid tokens receive general
  discovery results.
- Query parameters are `limit` (default `9`, clamped to `1..24`) and optional
  `product_id`, which is excluded from the result.
- Initial SQL candidates are products with `status == "Published"` and
  `stock > reserved_stock`. Final candidates must also satisfy
  `product_is_eligible`.
- For a consenting authenticated user, the last 500 events are loaded by
  `created_at.desc()`. There is no filter on event type, age, or
  `consent_snapshot` in this retrieval.
- `DISMISS` events add their product to the exclusion set. Other events become
  `(source_product, stored_weight)` signals. Events for missing products are
  skipped.
- For each remaining candidate, similarity to source products contributes:
  - same `category`: `+3.0`;
  - equal non-null `material`: `+2.0`;
  - equal non-null `style`: `+1.0`;
  - same `artisan_id`: `+2.0`.
  Each similarity contribution is multiplied by the stored event weight.
  Featured products add `+0.15`, and rating adds `rating / 50.0`.
- The final score is rounded to three decimals. Results are sorted by
  descending score, then ascending product ID, and truncated to `limit`.
- Each item returns `id`, `slug`, `name`, `image`, `price`, `category`,
  `artisan`, `score`, and `reason`. There is no score breakdown, request ID, or
  model version in the response.

No request ID is created for a recommendation response, no impression is
written server-side, and `recommendation_request_id` and `model_version` are
not used in ranking.

## 8. Frontend event reporting status

- `js/product.js` emits `PRODUCT_VIEW` once per product per browser session via
  `window.FabrixAPI.event`.
- `js/api-bridge.js` emits `FAVORITE_ADD` for newly added favorites and
  `CART_ADD` for newly added cart lines. It sends only `product_id`,
  `event_type`, and `event_id`.
- The bridge does not emit `FAVORITE_REMOVE` or `CART_REMOVE` even though it
  computes removals.
- No frontend code currently emits `RECOMMENDATION_IMPRESSION`,
  `RECOMMENDATION_CLICK`, or `DISMISS`.
- `js/app.js` contains a legacy `PURCHASE` event attempt. The server rejects it
  by design; trusted purchase events come only from checkout.
- `recommendations.html` is a static shell that loads `js/api-bridge.js` and
  `js/app.js`; it contains no inline event reporting.

## 9. Automated evidence

`tests/test_api.py` covers:

- `test_recommendations_respect_events` — aliases, duplicate IDs, conflicting
  IDs, and a basic response.
- `test_recommendation_purchase_events_are_server_only` — client `PURCHASE`
  rejection.
- `test_recommendation_events_respect_consent_and_attribution` — consent gate
  and anonymous private-event rejection.
- `test_impression_acknowledgment_and_privacy_controls` — impression request ID
  validation, duplicate acknowledgment, snapshot creation, retention cleanup,
  and user-data deletion.
- `test_suspended_store_products_are_not_purchasable` and
  `test_cart_sync_and_favorites_require_current_product_eligibility` — shared
  eligibility behavior.
- Checkout and idempotency tests indirectly exercise trusted purchase-event
  creation.

There are no dedicated tests yet for score-component math, dismissed-product
exclusion, stored context fields, retention audit rows, detailed snapshot
lineage, or frontend impression emission.

## 10. Status summary

| Capability | Status |
|---|---|
| Controlled event taxonomy | Implemented and tested |
| Event identity, attribution, timestamps, context, and weights | Implemented and tested |
| Server-only purchase events | Implemented and tested |
| Consent gate, opt-out, user-data deletion, retention cleanup | Implemented; deletion and retention have limited test depth |
| Basic snapshots, counts, exclusion reasons, and audit | Implemented and smoke-tested |
| Full reproducible lineage and dataset export | Not implemented |
| Shared product eligibility | Implemented and tested indirectly |
| Deterministic baseline scoring endpoint | Implemented and smoke-tested |
| Frontend impression/click/dismiss instrumentation | Not implemented |
| Seller/admin behavioral signal separation | Not implemented |
| Advanced Recommendation System | Not implemented; approved as new work |
