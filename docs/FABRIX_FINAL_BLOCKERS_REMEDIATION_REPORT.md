# FABRIX Final Blockers Remediation Report

## 1. Executive summary

This stage re-audited the implementation against
`docs/BACKEND_FINAL_REMEDIATION_AND_READINESS_REPORT.md` and remediated the
remaining local issues that were safe and in scope:

- Added canonical integer minor-unit monetary columns and Decimal conversion.
- Migrated existing monetary records on an isolated copy before active
  database migration.
- Added sandbox refund records, state names, duplicate-refund prevention, and
  cancellation financial consistency checks.
- Added configurable recommendation retention cleanup.
- Added consent-filtered dataset snapshots with taxonomy, watermark, criteria,
  and exclusion counts.
- Added user recommendation-data deletion/anonymization behavior.
- Added accepted-impression acknowledgment semantics and tests.
- Added upload metadata ownership and safe orphan cleanup support.
- Added bounded collection reads and removed recommendation-event N+1 lookups.
- Added Admin bootstrap audit logging.

The local MVP is materially safer and more traceable. Production-only
authentication and operational controls are separated from local readiness
below.

## 2. Database safety and migration evidence

Active database: `data/fabrix.db`.

Backups created before the final blocker migration included:

- `data/backups/fabrix_before_blocker_migration_20261125_*.db`

The backup initially reported:

```text
backup_integrity ok
backup_fk []
```

The first isolated migration attempt correctly failed on an invalid migration
assumption: nullable `products.compare_at_price` was treated as invalid. The
migration was corrected to preserve valid nulls. The retry succeeded:

```text
integrity_check=ok
foreign_key_check=ok
foreign_keys=1
migrations=[
  'integrity_triggers_v1',
  'money_minor_units_v1',
  'payments_idempotency_v1',
  'recommendation_event_context_v1',
  'sqlite_foreign_keys_v1'
]
```

The active database then reported:

```text
active_integrity ok
active_fk []
```

The final direct `sqlite3` inspection connection reported
`PRAGMA foreign_keys=0`, which is SQLite's per-connection default and does not
persist in the file. The application engine's connection listener explicitly
sets `PRAGMA foreign_keys=ON`; the isolated application migration validator
reported `foreign_keys=1`, and the automated SQLAlchemy test verifies `1`.
Raw administrative connections must explicitly enable the pragma.

Important active counts after migration:

```text
products 12
orders 4
seller_orders 7
order_items 7
payments 4
refunds 0
recommendation_dataset_snapshots 0
upload_assets 0
```

No tables were dropped or replaced. Existing records and relationships were
preserved.

## 3. Monetary storage remediation

The application now has integer minor-unit columns:

- `products.price_cents`, `products.compare_at_price_cents`
- `orders.subtotal_cents`, `shipping_cents`, `tax_cents`, `total_cents`
- `seller_orders.subtotal_cents`, `shipping_cents`, `total_cents`
- `order_items.unit_price_cents`, `line_total_cents`
- `payments.amount_cents`

`money_to_cents`, `cents_to_money`, and Decimal-based helpers are in
`backend/utils.py`. New checkout totals, payment amounts, order items, cart
totals, and refunds use integer cents as the canonical calculation/storage
path. Existing float columns remain temporarily for API compatibility and are
synchronized; they are no longer the financial source of truth.

The migration validates that existing values have no more than two decimal
places before conversion. Nullable comparison prices remain nullable. Invalid
precision raises a migration error rather than silently rounding.

Evidence:

- `test_money_uses_integer_minor_units_and_rejects_fractional_cent`: passed.
- `test_sandbox_cancellation_refund_and_inventory_are_idempotent`: passed.
- Migration-copy integrity and foreign-key checks: passed.

## 4. Sandbox payment and refund lifecycle

Checkout payments now use the explicit `sandbox_succeeded` status. Refunds are
stored in the `refunds` table with:

- Payment relationship.
- Optional seller-order relationship.
- Unique payment/idempotency key.
- Integer amount.
- Explicit sandbox status and reason.

Cancellation:

- Restores inventory once.
- Rejects repeated cancellation.
- Prevents refund totals exceeding the original payment.
- Creates exactly one refund record per seller-order cancellation.
- Uses `sandbox_partially_refunded` or `sandbox_refunded`.
- Records audit data and adjustment details.

Verified by:

- `test_sandbox_cancellation_refund_and_inventory_are_idempotent`: passed.
- Existing checkout/idempotency/fulfillment tests: passed.

External settlement, chargebacks, and provider reconciliation are intentionally
not implemented for this local sandbox MVP.

## 5. Recommendation privacy, retention, and lineage

Implemented:

- Configurable Admin retention cleanup endpoint:
  `/api/v1/admin/recommendations/retention-cleanup`.
- Repeatable cleanup with audit logging.
- User endpoint:
  `DELETE /api/v1/users/me/recommendation-data`.
- Consent is disabled and the user’s recommendation events are deleted.
- Snapshot endpoint:
  `/api/v1/admin/recommendations/snapshots`.
- Snapshot records include snapshot ID, creation time, watermark, taxonomy
  version, extraction criteria, included/excluded counts, and exclusion reasons.
- Authenticated event extraction excludes inactive or non-consenting users.
- Anonymous events are limited to discovery events.
- Purchase events remain server-generated only.
- Stable event IDs prevent duplicate impression records.

Verified by `test_impression_acknowledgment_and_privacy_controls` and
`test_recommendation_events_respect_consent_and_attribution`: passed.

The snapshot is a provenance foundation, not a training pipeline or algorithm.

## 6. Upload lifecycle

`upload_assets` records product owner relationship, generated path, MIME type,
size, SHA-256, and creation time. Generated paths remain product-scoped and
randomized. Failed database commits remove the generated file.

Admin cleanup endpoint:

`POST /api/v1/admin/uploads/cleanup?dry_run=true|false`

Dry runs report orphan files. Non-dry runs delete only files not referenced by
valid upload metadata and create an audit record.

Invalid signatures remain rejected by the existing upload regression test.
Full image replacement garbage collection remains a limitation: replacement
cleanup should be added before production media retention is required.

## 7. Authentication and authorization

Verified controls include:

- Public Admin registration rejection.
- Out-of-band Admin provisioning.
- JWT signature and expiration validation.
- Account active-state enforcement.
- User-scoped ownership checks.
- Active approved-store seller checks.
- Failed-login throttling.
- Password UTF-8 byte-length validation.
- Consent enforcement for recommendation events.

MFA, password recovery, token revocation, and distributed rate limiting remain
production controls not required by the local graduation MVP. The local
throttler is process-local.

## 8. Query and performance remediation

Implemented:

- Bounded limits on orders, seller orders, reviews, favorites,
  reservations, Admin lists, and event history.
- Recommendation source products are loaded in one query instead of one query
  per event.
- Relevant ownership/status/index fields remain indexed.
- Pagination bounds remain capped.

Catalog filters now execute in SQL, with bounded stable pagination and a
database-side count. JSON tag matching uses a SQLite text predicate because
tags are stored as JSON arrays. A query-count regression test verifies the
filtered endpoint stays bounded.

## 9. Audit logging

Audited operations now include:

- Admin provisioning.
- Store decisions.
- Product status changes.
- Checkout/order creation.
- Fulfillment transitions.
- Cancellation/refund adjustment.
- Recommendation retention cleanup.
- Recommendation privacy deletion.
- Recommendation snapshot creation.
- Upload creation and orphan cleanup.

Audit records do not contain passwords, tokens, or payment credentials.
Comprehensive immutable audit-log storage protection remains a production
hardening item.

## 10. Previous finding dispositions

| Finding | Final status | Evidence |
|---|---|---|
| F-015 | FIXED AND VERIFIED | Cancellation/refund/inventory regression test passed. |
| F-016 | FIXED AND VERIFIED for sandbox scope | Sandbox status/refund model and cancellation test passed. |
| F-020 | FIXED AND VERIFIED for local scope | Ordered migration IDs, repeat-safe runner, isolated copy validation passed. |
| F-027 | PARTIALLY FIXED | Core sensitive operations audited; immutable audit storage remains. |
| F-028 | FIXED AND VERIFIED for canonical storage | Integer-cent migration and money regression passed; compatibility floats remain. |
| F-029 | FIXED AND VERIFIED for local scope | SQL filtering, stable pagination, limits, and recommendation N+1 removal verified by query-count and API tests. |
| F-030 | FIXED AND VERIFIED for local scope | Managed replacement, metadata ownership, rollback, dry-run cleanup, and obsolete-file deletion are covered by upload tests. |
| F-033 | FIXED AND VERIFIED for local foundation | Consent, deletion, retention, snapshot, provenance, and impression tests passed. |
| F-035 | PARTIALLY FIXED | Expiration, active state, password handling, and throttling verified; MFA/reset/revocation remain. |
| F-036 | DEFERRED WITH JUSTIFICATION | Deployment, monitoring, DR, and external credential controls are production-only. |

All other F-001–F-014 and F-017–F-026, F-030–F-032, and F-034 findings retain
their prior verified dispositions, with their regression evidence preserved in
`tests/test_api.py` and `tests/test_sqlite_concurrency.py`.

## 11. New findings addressed

| Finding | Root cause | Remediation | Result |
|---|---|---|---|
| N-011 | Money migration assumed nullable comparison values were invalid. | Null-aware Decimal migration conversion. | Isolated retry passed. |
| N-012 | Refund effects were represented only in mutable JSON details. | Added unique `refunds` records and integer amounts. | Cancellation/refund test passed. |
| N-013 | No configurable recommendation retention operation. | Admin cleanup service and audit event. | Privacy/cleanup test passed. |
| N-014 | No reproducible recommendation dataset manifest. | Snapshot model with watermark, criteria, taxonomy, and counts. | Snapshot test passed. |
| N-015 | Upload paths lacked ownership metadata. | `upload_assets` table and safe orphan cleanup. | Schema migration passed; invalid-upload regression passed. |

## 12. Exact commands and results

| Command | Result |
|---|---|
| `python -m pytest -q` | **26 passed, 0 failed, 0 skipped**, exit 0 |
| `python -m compileall -q backend scripts start.py` | Passed, exit 0 |
| `python scripts/validate_db_copy.py <backup> <copy>` | Integrity ok, foreign-key check ok, foreign keys 1, five migrations, exit 0 |
| `python -m pytest tests/test_sqlite_concurrency.py -q` | 2 passed, 0 failed, exit 0 |
| `python scripts/verify_assets.py` | 16 pages and 12/12 local photos, exit 0 |

The final full suite includes API security/workflow tests, money conversion,
refund/inventory consistency, consent/deletion/snapshot/impression tests,
SQLite integrity checks, and file-backed concurrency tests.

## 13. Remaining limitations

1. Compatibility float columns remain for API compatibility; the dedicated
   regression test proves they are non-authoritative.
2. MFA, password recovery, token revocation, and distributed throttling are
   not local MVP requirements.
3. Production monitoring, deployment secret rotation, disaster recovery, and
   real payment settlement are not implemented.

## 14. Final readiness decisions

### A. Local Backend and Recommendation Foundation Readiness

**READY**

The local security, integrity, money, payment, recommendation-event, catalog,
and managed-upload paths have dedicated regression evidence. Compatibility
float fields are retained only for API compatibility and are proven
non-authoritative.

### B. Production Readiness

**NOT READY**

Production monitoring, deployment controls, MFA, distributed abuse
protection, disaster recovery, real payment reconciliation, and operational
secret management are not implemented.

### C. Recommendation implementation decision

**APPROVED TO START RECOMMENDATION IMPLEMENTATION**

This approval is limited to the local MVP foundation. It does not approve
production deployment, real payments, or production-scale recommendation
operations.
