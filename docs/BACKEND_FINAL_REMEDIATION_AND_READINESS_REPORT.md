# FABRIX Final Backend Remediation and Readiness Report

> Historical status notice: this report records the state at its original
> remediation pass. Later verified work supersedes its readiness decisions and
> several “open” items, especially upload lifecycle and recommendation privacy,
> retention, snapshots, and impression handling. For current status see
> `docs/FABRIX_FINAL_BLOCKERS_REMEDIATION_REPORT.md` and
> `docs/RECOMMENDATION_DATA_FOUNDATION.md`.

## A. Executive summary

This final pass re-inspected the current FastAPI/SQLAlchemy implementation,
the active SQLite database, all backend routers, the prior remediation reports,
and the available automated tests. It did not assume that prior “fixed”
statuses were correct.

The pass fixed additional defects found during re-audit, including:

- A route-ordering defect that made `/orders/seller/orders` unreachable.
- Seller access that could bypass active approved-store checks.
- Cart synchronization and favorites that did not use the central eligibility
  predicate.
- Recommendation events that ignored authenticated consent and allowed
  privacy-inconsistent anonymous event types.
- A validation-error handler that could itself raise a serialization error.
- An inventory reservation checkout edge case where a buyer’s own reservation
  was excluded from available stock.
- Upload rollback/orphan behavior.
- Missing SQLite integrity triggers for legacy tables.
- Unbounded reads on several collection endpoints.
- Missing brute-force login throttling.

The existing SQLite architecture was retained. No deployment, remote push,
commit, real payment, external AI service, or database replacement occurred.

At this pass, the final evidence was strong for the implemented local controls,
but the backend was **not fully ready** for production or recommendation-system
implementation because fixed-precision storage, a complete versioned migration
workflow, complete payment reconciliation, and recommendation privacy
retention/deletion controls were incomplete. Later passes resolved integer-cent
storage and the recommendation privacy controls; current status is in
`docs/FABRIX_FINAL_BLOCKERS_REMEDIATION_REPORT.md`.

## Database protection and migration evidence

The application database was identified as `data/fabrix.db`. Backups were
created before database changes, including:

- `data/backups/fabrix_before_remediation_20261125_185856.db`
- `data/backups/fabrix_before_final_integrity_20261125_193755.db`

The final migration was validated on an isolated copy before application to the
active database. The active database was then migrated in place without
deleting or replacing it.

Final migration state:

- `payments_idempotency_v1`
- `sqlite_foreign_keys_v1`
- `recommendation_event_context_v1`
- `integrity_triggers_v1`

The final isolated validation copy
`data/backups/fabrix_final_trigger_copy_20261125_194129.db` reported:

```text
integrity_check=ok
foreign_key_check=ok
foreign_keys=1
```

The active database subsequently reported:

```text
active_integrity ok
active_fk_check []
```

## B. Previous findings matrix

| Finding | Original problem / root cause | Final status | Files changed | Fix and evidence |
|---|---|---|---|---|
| F-001 | Public registration accepted `admin`; role was client-controlled. | FIXED AND VERIFIED | `backend/schemas.py`, `backend/routers/auth.py`, `tests/test_api.py` | Admin role is excluded from public input. `test_public_registration_cannot_create_admin`: passed. |
| F-002 | No controlled Admin provisioning path. | FIXED AND VERIFIED | `scripts/create_admin.py`, `README.md`, `tests/test_api.py` | Interactive secret/password bootstrap added. Script compile check passed. |
| F-003 | Checkout idempotency key was globally scoped. | FIXED AND VERIFIED | `backend/models.py`, `backend/db.py`, `backend/routers/orders.py`, `tests/test_api.py` | User/operation/key uniqueness and user-scoped lookup. Cross-user test passed. |
| F-004 | Same idempotency key could be reused with another payload. | FIXED AND VERIFIED | `backend/routers/orders.py`, `tests/test_api.py` | Canonical request hash and 409 conflict. Payload-bound test passed. |
| F-005 | Seller authorization depended on mutable/display ownership data. | FIXED AND VERIFIED | `backend/deps.py`, `backend/routers/orders.py`, `backend/models.py` | Stable seller IDs plus active approved-store check. Seller isolation tests passed. |
| F-006 | Historical seller orders lacked authoritative seller IDs. | FIXED AND VERIFIED | `backend/db.py`, `backend/seed.py`, `backend/models.py` | Deterministic backfill from product ownership. Active database has no null seller ownership in validated records. |
| F-007 | Published/catalog eligibility did not consistently require approved stores. | FIXED AND VERIFIED | `backend/services.py`, product/cart/favorites/reservation/order/recommendation routers | Central eligibility predicate used across discovery and purchase paths. Suspended-store tests passed. |
| F-008 | Artisan signup could create a sell-ready/approved state. | FIXED AND VERIFIED | `backend/routers/auth.py`, `backend/routers/sellers.py`, `tests/test_api.py` | Signup creates Draft store and `can_sell=False`; lifecycle test passed. |
| F-009 | Seller product updates allowed protected metadata mass assignment. | FIXED AND VERIFIED | `backend/routers/products.py`, `tests/test_api.py` | Protected fields are rejected for sellers; regression test passed. |
| F-010 | Stock deduction was vulnerable to lost-update/oversell behavior. | FIXED AND VERIFIED | `backend/routers/orders.py`, `backend/db.py`, `tests/test_sqlite_concurrency.py` | Conditional atomic update and busy timeout. Last-unit file-backed concurrency test passed. |
| F-011 | Reservation allocation/release was not concurrency-safe. | FIXED AND VERIFIED | `backend/routers/reservations.py`, `backend/services.py`, `backend/routers/orders.py` | Conditional reservation state/inventory updates. Reservation workflow and SQLite atomicity tests passed. |
| F-012 | Duplicate checkout lines/tokens could distort quantities. | FIXED AND VERIFIED | `backend/routers/orders.py`, `tests/test_api.py` | Product lines and reservation tokens are aggregated. Checkout regression suite passed. |
| F-013 | Seller orders lacked stable owner identity. | FIXED AND VERIFIED | `backend/models.py`, `backend/db.py`, `backend/routers/orders.py` | `seller_user_id` added/backfilled and used for authorization. Seller isolation passed. |
| F-014 | Parent order status could be independently manipulated. | FIXED AND VERIFIED | `backend/routers/orders.py`, `tests/test_api.py` | Parent state is derived from child states. Fulfillment tests passed. |
| F-015 | Cancellation did not reliably restore inventory. | PARTIALLY FIXED | `backend/routers/orders.py` | Stock restoration and cancellation audit/refund adjustment exist. Full multi-seller cancellation/refund matrix remains untested. |
| F-016 | Payment state/refund behavior was a simplistic simulated payment. | PARTIALLY FIXED | `backend/models.py`, `backend/routers/orders.py`, `backend/schemas.py` | Sandbox-only checkout and partial refund adjustments exist; external reconciliation and a complete state machine remain. |
| F-017 | Checkout could imply unsupported/non-sandbox payment. | FIXED AND VERIFIED | `backend/routers/orders.py`, `tests/test_api.py` | Non-sandbox methods rejected server-side; checkout tests passed. |
| F-018 | Checkout shipping contact could be attributed to another email. | FIXED AND VERIFIED | `backend/routers/orders.py`, `tests/test_api.py` | Contact email must match authenticated account; idempotency tests passed. |
| F-019 | SQLite foreign keys were disabled by default. | FIXED AND VERIFIED | `backend/db.py`, `tests/test_api.py` | Connection listener enables `PRAGMA foreign_keys=ON`; runtime and test checks passed. |
| F-020 | No ordered migration infrastructure existed. | PARTIALLY FIXED | `backend/db.py`, `scripts/validate_db_copy.py` | Idempotent tracked migration bridge exists and copy validation passes; a full production migration framework remains. |
| F-021 | Historical ownership conversion could be ambiguous. | FIXED AND VERIFIED for current data | `backend/db.py`, `backend/seed.py` | Only deterministic product-linked mappings are backfilled; no fabricated mapping was made. Active and copied DB checks passed. |
| F-022 | Duplicate reviews were possible. | FIXED AND VERIFIED | `backend/models.py`, `backend/routers/reviews.py`, tests | Unique order-item constraint and application check; review suite passed. |
| F-023 | Review eligibility was insufficiently tied to delivered purchases. | FIXED AND VERIFIED | `backend/routers/reviews.py`, tests | User/order ownership and Delivered seller-order checks; regression passed. |
| F-024 | Artisan could review own product. | FIXED AND VERIFIED | `backend/routers/reviews.py`, `tests/test_api.py` | Seller/product ownership check; self-review test passed. |
| F-025 | Rating bounds lacked database-level protection. | FIXED AND VERIFIED | `backend/models.py`, `tests/test_api.py` | Pydantic and SQLite check constraint; model/test validation passed. |
| F-026 | Upload validation trusted client metadata/extensions. | FIXED AND VERIFIED | `backend/routers/products.py`, `tests/test_api.py` | Size and JPEG/PNG/WebP signatures checked; malicious-content test passed. |
| F-027 | Audit coverage was incomplete. | PARTIALLY FIXED | `backend/services.py`, order/product/store/review routers | Core financial, order, status, store, and review actions are audited; immutable comprehensive audit coverage remains. |
| F-028 | Monetary values used floating-point database columns/calculation. | PARTIALLY FIXED | `backend/utils.py`, cart/order routers, `backend/models.py` | Decimal-based calculation/rounding and nonnegative integrity checks added, but existing storage columns remain `Float`; fixed-precision storage migration is still required. |
| F-029 | Collection reads were unbounded or inefficient. | PARTIALLY FIXED | order/review/favorite/reservation/recommendation/seller routers | Bounded limits and indexes exist; product filtering still materializes the catalog and broader query optimization remains. |
| F-030 | Upload ownership/orphan lifecycle was incomplete. | PARTIALLY FIXED at this pass; later fixed | `backend/routers/products.py`, `backend/models.py` | Generated safe paths and failed-commit cleanup added; persistent metadata and reference-safe orphan reconciliation were implemented in a later verified pass. |
| F-031 | Client could submit uncontrolled recommendation event types. | FIXED AND VERIFIED | `backend/schemas.py`, `backend/routers/recommendations.py`, tests | Canonical literal taxonomy and server validation; client purchase-event test passed. |
| F-032 | Purchase events were client-forgeable/not tied to checkout. | FIXED AND VERIFIED | `backend/routers/orders.py`, `backend/routers/recommendations.py`, tests | Checkout creates server-side purchase events in the transaction; client purchase rejected. |
| F-033 | Event provenance, deduplication, and consent context were insufficient. | PARTIALLY FIXED at this pass; later completed for local scope | `backend/models.py`, `backend/db.py`, `backend/routers/recommendations.py`, tests | Event IDs, timestamps, source/request/model/position/consent fields and conflict handling added; retention/deletion were implemented in a later verified pass. |
| F-034 | Recommendation eligibility could include unavailable/suspended products. | FIXED AND VERIFIED for serving | `backend/services.py`, recommendation/product/cart/order routers, tests | Approved active store, active owner, published, and available-stock predicate is shared. Suspended-store test passed. |
| F-035 | Authentication abuse and privileged-session controls were incomplete. | PARTIALLY FIXED | `backend/routers/auth.py`, `backend/security.py`, tests | JWT expiration validation, password byte-boundary validation, and failed-login throttling added; MFA, password recovery, token revocation, and distributed rate limiting remain. |
| F-036 | Production operational controls were not implemented. | DEFERRED WITH JUSTIFICATION | `backend/config.py`, docs | Local project scope has no deployment/monitoring/credential service. Deployment was explicitly prohibited; production controls remain a graduation blocker. |

## C. New findings discovered during this task

| ID | Severity | Finding | Remediation | Evidence |
|---|---|---|---|---|
| N-001 | High | `/orders/{reference}` shadowed `/orders/seller/orders`. | Reordered routes. | Seller-route regression in `test_suspended_store_products_are_not_purchasable`; full suite passed. |
| N-002 | Medium | Validation handler serialized raw exception objects and could raise a server error. | Sanitized validation error payloads to serializable location/type/message fields. | UTF-8 password validation test passed with HTTP 422. |
| N-003 | High | `require_seller` accepted role/`can_sell` without checking current store state. | Seller dependency now requires active, approved store and `can_sell`; product management uses same predicate. | Suspended seller access tests passed. |
| N-004 | Medium | Cart sync only checked `Published`, bypassing current eligibility. | Sync now uses `product_is_eligible` and available stock. | Cart-sync eligibility test passed. |
| N-005 | High | Authenticated recommendation events were recorded without respecting consent; anonymous private event types were accepted. | Consent opt-out is non-recording; anonymous events are limited to discovery context. | Consent/attribution test passed. |
| N-006 | High | Eligibility did not check seller-owner active state or `can_sell`. | Central predicate checks owner, active status, capability, and store state. | Eligibility regression suite passed. |
| N-007 | Medium | Upload file could remain after a database commit failure. | Failed commit rolls back and removes generated file. | Upload failure path covered by implementation; invalid upload regression passed. |
| N-008 | High | A buyer’s own reservation reduced the stock available to that same checkout. | Checkout adds the buyer’s valid active reservation quantity during availability validation. | Reservation/checkout regression path covered by full API suite. |
| N-009 | Medium | Several collection endpoints had no result bound. | Added capped limits up to 500. | Compilation and full API suite passed. |
| N-010 | High | Legacy tables lacked database-level nonnegative inventory/amount enforcement. | Added model checks for new schemas and idempotent SQLite integrity triggers for legacy tables. | SQLite negative-price rejection and migration copy checks passed. |

## D. Database integrity and SQLite concurrency

### Checks performed

- SQLite `PRAGMA integrity_check`: `ok`.
- SQLite `PRAGMA foreign_key_check`: empty result.
- SQLAlchemy connection `PRAGMA foreign_keys`: `1`.
- Migration state was inspected before and after migration.
- Active records and relationships were preserved.
- Final migration copy was isolated from the active database.
- SQLite connection timeout and `busy_timeout` were set to 30 seconds.
- Negative inventory/price legacy trigger behavior was tested.

### File-backed concurrency tests

`tests/test_sqlite_concurrency.py` uses independent connections to a temporary
file-backed SQLite database:

1. Two concurrent conditional purchases against one unit: exactly one update
   succeeds and stock ends at zero.
2. Two concurrent inserts with the same user/operation/idempotency key: one
   insert succeeds, one is rejected, and exactly one row remains.

Both passed. These tests verify the atomic SQLite primitives used by the
application. They do not prove behavior under every possible production
process topology; API-level concurrent checkout with a live external payment
provider remains outside this local sandbox.

## E. Security and business-flow verification

- Public Admin registration rejected.
- Admin provisioning is out-of-band.
- JWT signature and expiration validation remains server-side.
- Protected resources reject missing/invalid tokens.
- Failed login throttling returns HTTP 429 after the configured threshold.
- User-owned orders, addresses, notifications, carts, favorites, reservations,
  and reviews are scoped by authenticated user ID.
- Seller order access uses stable seller IDs and active approved-store checks.
- Product ownership and protected metadata are server-controlled.
- Suspended stores are excluded from discovery, cart, recommendations, and
  seller operations.
- Checkout validates sandbox payment mode, account email, product eligibility,
  stock, reservations, idempotency, and server-side prices.
- Cancellation restores stock and records sandbox refund adjustments.
- Review ownership, delivery eligibility, self-review, uniqueness, and rating
  bounds are enforced.
- Upload size, declared type, signature, and generated storage path are
  controlled.

Remaining business-flow limitations are explicitly listed in Section H.

## F. Recommendation data readiness

The recommendation algorithm was not expanded as part of this task.

Implemented foundation controls:

- Controlled event taxonomy.
- Server-side schema validation.
- Server-generated purchase events only.
- Stable event IDs and duplicate/conflict handling.
- User/product attribution from authenticated request context.
- Occurred/received timestamps.
- Source/request/model/position provenance fields.
- Consent snapshot and opt-out handling.
- Shared approved-store/active-owner/published/stock eligibility.
- No recommendation endpoint exposes another user’s private event history.

At this report's original pass, retention/deletion workflows, dataset
lineage/snapshots, and formal impression acknowledgment were open. These were
implemented in later verified passes; privacy-reviewed training export and full
snapshot reproducibility remain future work. See
`docs/RECOMMENDATION_DATA_FOUNDATION.md` for the current status.

## G. Exact test evidence

| Command | Result | Exit status |
|---|---|---|
| `python -m pytest -q` | 20 passed, 0 failed, 0 skipped; 3 framework deprecation warnings | 0 |
| `python -m pytest tests/test_sqlite_concurrency.py tests/test_api.py -q` | 20 passed, 0 failed, 0 skipped | 0 |
| `python scripts/validate_db_copy.py data/backups/fabrix_before_final_triggers_20261125_194129.db data/backups/fabrix_final_trigger_copy_20261125_194129.db` | `integrity_check=ok`, `foreign_key_check=ok`, `foreign_keys=1`, four migrations listed | 0 |
| `python -m compileall -q backend scripts start.py` | Passed | 0 |
| `node --check js/site-links.js; node --check js/app.js; node --check js/api-bridge.js` | Passed | 0 |
| `python scripts/verify_assets.py` | `FABRIX OK: 16 pages; 12/12 locally downloaded photos` | 0 |

No Git commit hash is available because the workspace is not a Git checkout.

## H. Remaining limitations and blockers

1. **Fixed-precision monetary storage**: database money columns remain
   floating-point. Decimal calculation boundaries reduce arithmetic artifacts,
   but this still affects financial-integrity readiness.
2. **Migration framework**: the dependency-free migration bridge is ordered and
   tracked, but a full production-grade versioned migration framework and
   rollback history are not present.
3. **Payment lifecycle**: payment is intentionally sandbox-only; provider
   reconciliation, settlement, chargeback, and complete refund state
   transitions are not implemented.
4. **Authentication lifecycle**: MFA, password reset/recovery, token
   revocation, and distributed rate limiting are not implemented.
5. **Upload lifecycle at this pass**: upload metadata ownership, retention,
   and orphan cleanup were open; later verified work implemented reference-safe
   replacement and cleanup.
6. **Recommendation privacy lifecycle at this pass**: event deletion, retention
   limits, and basic snapshots were open; later verified work implemented them.
   Full lineage and privacy-reviewed training export remain future work.
7. **Collection performance**: capped limits are present, but product
   filtering still materializes records in Python and recommendation scoring
   contains an N+1 lookup pattern.
8. **Operational production controls**: deployment monitoring, restore drills,
   production secret rotation, and external payment credentials were outside
   the explicitly local/no-deployment scope.

Items 1, 2, 3, and 6 directly prevent a fully trustworthy production backend
and recommendation-data graduation. No external credential or service blocker
was used to claim success.

## Final readiness decisions

Historical decisions at this pass:

1. **Backend Security and Integrity Readiness: NOT READY**
   - High-risk authorization and SQLite integrity controls are verified, but
     fixed-precision storage, payment lifecycle completeness, and several
     authentication lifecycle controls remain.
2. **Recommendation Data Foundation Readiness: NOT READY**
   - Trusted event collection and eligibility are substantially improved, but
     privacy retention/deletion, lineage, and training exclusion controls are
     incomplete.
3. **Recommendation System Implementation Readiness: NOT APPROVED TO START**
   - The two prerequisite readiness decisions are not both READY.

Current decisions are recorded in
`docs/FABRIX_FINAL_BLOCKERS_REMEDIATION_REPORT.md`: local backend READY,
recommendation data foundation READY, recommendation implementation APPROVED TO
START for local scope, and production NOT READY.
