# FABRIX Recommendation System Developer Handoff

This handoff is for the developer who will implement the advanced Recommendation
System. It describes what already exists, what is only a baseline, and what is
new work. Do not replace the existing data foundation or invent new API fields
without updating the OpenAPI contract and tests.

The authoritative background documents are:

- `docs/RECOMMENDATION_DATA_FOUNDATION.md` — implemented data foundation.
- `docs/FABRIX_FINAL_BLOCKERS_REMEDIATION_REPORT.md` — verification and
  readiness evidence.
- `README.md` — fresh-clone setup and test commands.

## A. Project overview

FABRIX is a local-first handmade marketplace. Customers browse and buy products;
artisans own stores and publish products; the backend records permitted
interaction events and serves recommendations. Recommendation events connect a
user (or an anonymous session), a product, an event type, a weight, and context
such as source, display position, and consent snapshot.

The local MVP uses FastAPI, SQLAlchemy, SQLite, and a static frontend. Payments
are sandbox-only. The goal of this handoff is to let a new developer clone the
repository, run the project, understand the implemented event pipeline, and
begin advanced recommendation work without needing another developer's local
database.

The current `GET /api/v1/recommendations` endpoint is a deterministic baseline
scorer. It is not a completed advanced Recommendation System.

## B. Current implementation status

| Component | Relevant files | Current behavior | Status | Remaining work |
|---|---|---|---|---|
| Recommendation API | `backend/routers/recommendations.py`, `backend/schemas.py` | Event ingestion, baseline scoring, retention cleanup, snapshot creation | Implemented baseline | Request IDs, richer response metadata, advanced ranking, read/export endpoints |
| Recommendation data models | `backend/models.py`, `backend/db.py` | Event and snapshot tables, unique event IDs, provenance columns, migrations | Implemented | Immutable source manifest, export artifact, model/code version hash |
| Event collection | `backend/routers/recommendations.py`, `js/api-bridge.js`, `js/product.js` | Eight client event types with alias normalization, validation, dedup, consent gate | Implemented, partially instrumented | Frontend remove/impression/click/dismiss events, context fields, timestamp hygiene |
| Purchase-event generation | `backend/routers/orders.py` | Checkout writes server-only `PURCHASE` events with deterministic IDs in the same transaction | Implemented | Optional richer context; audit correctness for purchase events |
| Consent and privacy | `backend/routers/users.py`, `backend/routers/auth.py`, `backend/services.py` | `consent` gate for event recording/serving, opt-out update, user-data deletion, retention cleanup, snapshot exclusion | Implemented; `personalization` not enforced server-side | Enforce `personalization` if required, role-separated signals, deeper privacy tests |
| Dataset snapshots | `backend/services.py`, `backend/models.py` | Basic snapshot with watermark, static criteria, counts, exclusion reasons, audit row | Implemented minimum | Snapshot read/list, frozen event manifest, train/validation/test export, real retention exclusion |
| Product eligibility | `backend/services.py` and its callers | Shared published/stock/owner/active/approved-store predicate | Implemented | Normalized product taxonomy and richer availability semantics, if needed |
| Baseline scoring logic | `backend/routers/recommendations.py` | Category, material, style, artisan, featured, rating; sorted by score then ID | Implemented baseline | Offline evaluation, candidate generation strategy, cold start, ranking improvements |
| Frontend integration | `js/api-bridge.js`, `js/app.js`, `js/product.js`, `recommendations.html` | Recommendations fetched unconditionally; product-view/favorite-add/cart-add reported | Partial | Impression/click/dismiss and remove-event instrumentation, request correlation |

The data foundation is ready. The advanced Recommendation System is approved
as new work, but this task does not implement it.

## C. Architecture and data flow

### Current flow

1. A user interacts with a product or a recommendation surface.
2. `js/product.js` sends `PRODUCT_VIEW`; `js/api-bridge.js` sends
   `FAVORITE_ADD` and `CART_ADD`. The bridge sends only `product_id`,
   `event_type`, and `event_id`.
3. `POST /api/v1/recommendations/events` validates the taxonomy and aliases,
   requires authentication for private event types, requires a request ID for
   impressions, checks product eligibility, enforces consent, deduplicates by
   `event_id`, and stores the event with server-owned attribution and context.
4. Checkout in `backend/routers/orders.py` creates trusted `PURCHASE` events
   after order records are built, in the same transaction as the order and
   payment records. Clients cannot submit purchase events.
5. `GET /api/v1/recommendations` reads the last 500 events only for a consenting
   authenticated user. Anonymous or non-consenting users get general discovery.
   `DISMISS` events exclude products.
6. Remaining eligible candidates are scored with the baseline similarity rules
   and returned with a score and human-readable reason.
7. Admin endpoints create a snapshot or run retention cleanup. A user can
   delete their own recommendation events.

### Proposed future architecture

Keep the existing ingestion, consent, eligibility, and snapshot endpoints as the
foundation. Add, as separate new work:

- privacy-filtered dataset extraction with a frozen source manifest;
- offline train/validation/test evaluation;
- candidate generation independent of the final ranker;
- scoring/ranking that consumes explicit feature definitions and versioning;
- response metadata that can be correlated with impression and click events;
- reproducible evaluation reports before replacing the baseline endpoint.

Do not couple the frontend directly to a model implementation. Preserve the
existing OpenAPI contract or version it deliberately.

## D. Important source files

All paths are project-relative.

- `backend/models.py` — `RecommendationEvent`,
  `RecommendationDatasetSnapshot`, `Product`, `User`, `Store`, and `AuditLog`
  definitions; relationship and uniqueness rules.
- `backend/schemas.py` — `RecommendationEventIn`, `RecommendationOut`,
  `RecommendationList`, `RecommendationSnapshotOut`, `LoginRequest`,
  `UserUpdate`, and `Message`; authoritative request/response shapes.
- `backend/routers/recommendations.py` — all event, serving, retention, and
  snapshot routes; `EVENT_WEIGHTS`; baseline scoring.
- `backend/routers/orders.py` — checkout, idempotency, and trusted purchase
  event creation.
- `backend/services.py` — `product_is_eligible`, retention cleanup, privacy
  extraction, snapshot creation, and audit helper.
- `backend/routers/users.py` — consent update and
  `DELETE /api/v1/users/me/recommendation-data`.
- `backend/routers/auth.py` — registration consent/personalization fields and
  login behavior.
- `backend/deps.py` — `OptionalUser`, `CurrentUser`, `DbSession`, and
  `require_admin` behavior.
- `backend/seed.py` — idempotent demo users and products.
- `backend/main.py` — app lifespan, validation errors, router registration,
  health endpoint, and static page serving.
- `backend/config.py` — API prefix, database URL, secret, and CORS settings.
- `backend/db.py` — SQLite foreign-key pragmas, table creation, and schema
  migrations including recommendation event context columns.
- `backend/utils.py` — `utcnow()` and order-number generation used by event
  IDs and timestamps.
- `js/api-bridge.js` — API detection, token hydration, and event forwarding.
- `js/app.js` — recommendation fetch, consent controls, and legacy purchase
  event attempt that the server correctly rejects.
- `js/product.js` — product-view event emission.
- `recommendations.html` — recommendation page shell.
- `tests/test_api.py` — all recommendation, privacy, eligibility, and checkout
  tests.
- `docs/RECOMMENDATION_DATA_FOUNDATION.md` — detailed current behavior and
  limitations.

## E. API contracts

`/docs` and `/openapi.json` are authoritative. All paths below are under
`/api/v1`.

| Method and path | Request | Response | Auth | Notable errors |
|---|---|---|---|---|
| `POST /recommendations/events` | `RecommendationEventIn` | `Message`, 201 | Optional; private types require a real user | 422 invalid taxonomy/payload or impression without request ID; 401 private anonymous event; 404 ineligible product; 409 conflicting event ID |
| `GET /recommendations` | Query `limit=9`, optional `product_id` | `RecommendationList`, 200 | Optional | 422 invalid query types; `limit` is clamped to `1..24` |
| `POST /admin/recommendations/retention-cleanup` | Query `retention_days=90` | `Message`, 200 | Admin | 401/403; 400 outside `1..3650` |
| `POST /admin/recommendations/snapshots` | No body | `RecommendationSnapshotOut`, 201 | Admin | 401/403 |
| `DELETE /users/me/recommendation-data` | No body | `Message`, 200 | Authenticated user | 401 |
| `PATCH /users/me` | `UserUpdate` including `personalization` and `consent` | `UserOut`, 200 | Authenticated user | 401/422 |
| `POST /orders/checkout` | `CheckoutRequest` | `OrderOut`, 201 | Authenticated user | 400 invalid method/cart/email; 404 ineligible product; 409 stock or idempotency conflict |
| `GET /admin/audit` | Query `limit` | `AuditLogList`, 200 | Admin | 401/403; `limit` clamped to `1..500` |

`RecommendationOut` fields are `id`, `slug`, `name`, `image`, `price`,
`category`, `artisan`, `score`, and `reason`. `RecommendationList` has only
`items`. `RecommendationSnapshotOut` has `snapshot_id`, `created_at`,
`watermark`, `taxonomy_version`, `criteria`, `included_count`,
`excluded_count`, and `exclusion_reasons`.

Validation errors use the application-wide shape
`{"detail":"Invalid request","errors":[...]}`. A duplicate event is a 201
no-op; only conflicting reuse of an event ID is a 409.

## F. Current database entities

- `users` — identity, role, `is_active`, `can_shop`, `can_sell`, `consent`,
  and `personalization`. `consent` is used by event recording, serving, and
  snapshot extraction.
- `products` — `id`, `slug`, `name`, `category`, `material`, `style`, `tag`,
  `materials`, `tags`, `artisan_id`, `status`, `stock`, `reserved_stock`,
  `rating`, `featured`, image fields, and integer minor-unit prices.
  `available_stock` is derived as `max(stock - reserved_stock, 0)`.
- `recommendation_events` — `id`, unique `event_id`, optional `user_id`
  (foreign key to `users`, cascade delete), required `product_id` (foreign key
  to `products`, cascade delete), `event_type`, `weight`, `occurred_at`,
  `received_at`, `created_at`, `session_id`, `source_context`,
  `recommendation_request_id`, `model_version`, `position`, and
  `consent_snapshot`.
- `recommendation_dataset_snapshots` — `snapshot_id`, `created_at`,
  `watermark`, `taxonomy_version`, `criteria`, `included_count`,
  `excluded_count`, and `exclusion_reasons`.
- `audit_logs` — audit actions including `recommendation.privacy_deleted`,
  `recommendation.retention_cleanup`, `recommendation.snapshot.created`, and
  `order.created`.

Events relate to users and products by foreign keys. Anonymous events have a
null `user_id` and `consent_snapshot=False`. Snapshots record aggregate
provenance but do not store the included event IDs or a frozen event copy;
later deletions can change the underlying source data.

## G. Recommended implementation roadmap

These stages are guidance, not a prescribed algorithm. Evaluate the existing
baseline, available event volume, project requirements, and local hardware
before choosing a strategy.

1. **Requirements and strategy.** Define success metrics and product goals.
   Inventory what the current event volume can support; do not assume deep
   learning is justified locally.
2. **Candidate generation.** Decide how eligible products enter the candidate
   set. Reuse `product_is_eligible`. Consider popularity, recency, category,
   artisan, cart/favorite signals, and cold-start fallback separately.
3. **Scoring and ranking improvements.** Replace hard-coded similarity scores
   only after an evaluation harness exists. Record feature definitions and
   versioning. Keep the deterministic baseline as a fallback.
4. **User preference and behavioral signal handling.** Define how each event
   type and weight contributes, including negative `DISMISS` signals. Decide
   whether `FAVORITE_REMOVE` and `CART_REMOVE` should cancel prior signals.
   Validate consent and `personalization` semantics.
5. **Product and category similarity.** Evaluate plain attributes, tags,
   materials, styles, artisans, and text features. Do not invent normalized
   taxonomy tables unless the benefit is demonstrated.
6. **Cold-start behavior.** Define general discovery for guests, new users,
   non-consenting users, new products, and products with few events. The
   current endpoint already has a general-discovery path.
7. **Recommendation explanations.** The baseline returns a single `reason`
   string. If richer explanations are required, version the response contract
   rather than silently changing it.
8. **API integration.** Keep request IDs, model versions, and ranking versions
   explicit. Decide whether to add response metadata, snapshot read endpoints,
   and export endpoints. Update OpenAPI-visible schemas and tests together.
9. **Frontend integration.** Add impression, click, dismiss, and remove-event
   instrumentation. Correlate events with the request ID returned by the API.
   Remove or replace the legacy rejected `PURCHASE` call in `js/app.js`.
10. **Automated testing.** Add unit tests for feature extraction and scoring,
    API tests for new contracts, privacy tests for exclusion paths, and
    regression tests for the baseline fallback.
11. **Quality evaluation.** Build offline train/validation/test splits from
    privacy-filtered data. Compare against the current baseline with documented
    metrics and error analysis before promoting a new ranker.
12. **Performance and privacy verification.** Measure endpoint latency and
    database query counts. Verify no endpoint leaks another user's events,
    that deleted events are excluded, and that snapshots reproduce documented
    behavior.

## H. Testing and acceptance criteria

Install test dependencies and run the suites sequentially:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q backend tests scripts start.py
python scripts/verify_assets.py
python -m pytest -q
python -m pytest tests/test_upload_lifecycle.py -q
python -m pytest tests/test_sqlite_concurrency.py -q
python scripts/validate_db_copy.py data/fabrix.db "$env:TEMP/fabrix-validation.db"
```

Do not run parallel pytest processes; the API tests share a temporary SQLite
database.

Existing recommendation tests in `tests/test_api.py`:

- `test_recommendations_respect_events`
- `test_recommendation_purchase_events_are_server_only`
- `test_recommendation_events_respect_consent_and_attribution`
- `test_impression_acknowledgment_and_privacy_controls`
- `test_suspended_store_products_are_not_purchasable`
- `test_cart_sync_and_favorites_require_current_product_eligibility`

New implementation work must add tests for:

- score-component math and deterministic tie-breaking;
- dismissed-product exclusion;
- consent false, opt-out, and post-deletion behavior;
- retention cutoff and audit rows;
- snapshot counts, exclusion reasons, and any new export manifest;
- request ID and model/version correlation;
- frontend emission of impression, click, dismiss, and remove events;
- absent or ineligible products in candidate results;
- no cross-user event disclosure;
- reproducible output for a fixed fixture and version.

Quality acceptance should compare the new system against the existing baseline
on a documented offline dataset and report metrics appropriate to the chosen
strategy. Reproducibility requires fixed event fixtures, recorded versions, and
stable tie-breaking; it does not require sharing the original developer's
database.

## I. Explicit non-goals

This work does not authorize:

- real payment provider integration or settlement;
- public production deployment or hosted infrastructure;
- paid external AI services;
- replacing SQLite with another database as part of recommendation work;
- implementing recommendation algorithms as part of this handoff task;
- sharing the active local database or personal event history;
- weakening consent, deletion, retention, or product-eligibility controls.
