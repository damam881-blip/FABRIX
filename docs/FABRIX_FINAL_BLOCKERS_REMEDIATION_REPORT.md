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
- Added upload metadata ownership, managed replacement cleanup, and orphan
  cleanup support.
- Added bounded collection reads and removed recommendation-event N+1 lookups.
- Added Admin bootstrap audit logging.

The local MVP is materially safer and more traceable. An intermediate
documentation-only consistency check found that the earlier upload readiness
claim was broader than the automated evidence. The focused remediation recorded
in Section 6 subsequently closed that gap with reference-safe cleanup, exact
dry-run reporting, retry-safe deletion, and 17 dedicated regression tests.
Production-only authentication and operational controls remain separated from
local readiness below.

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

Implemented and inspected in `backend/routers/products.py`,
`backend/services.py`, `backend/routers/sellers.py`, and `backend/schemas.py`,
with dedicated regressions in `tests/test_upload_lifecycle.py`:

- New uploads are validated by MIME type, suffix, byte size, and image
  signature before any product mutation or database write.
- Files are written to a randomized, product-scoped path under the canonical
  root `assets/uploads/products/<product_id>/`.
- `upload_assets` records product ownership, absolute path, MIME type, size,
  SHA-256, and creation time.
- Product image fields and upload metadata are staged in one database
  transaction. If `db.commit()` fails, the transaction is rolled back, the new
  file is unlinked, and the previous product image reference remains intact.
- Replacement computes obsolete managed paths from the previous `Product.images`
  and `Product.image` values before mutation, commits the new reference first,
  then runs the shared cleanup restricted to those paths. Cleanup re-checks all
  product references, so an image shared by another product or another image
  entry is protected.
- `inspect_upload_cleanup` normalizes `/assets/uploads/products/...` URLs,
  absolute paths, and stored metadata paths; resolves them against the
  canonical upload root; rejects traversal and outside-root references; and
  classifies files without mutating disk or database state. Legacy
  `/assets/photos/...` references are reported as `legacy_references` and are
  preserved, not treated as upload-root escapes.
- Cleanup distinguishes managed assets, valid referenced files, referenced
  legacy files without metadata, unreferenced generated files, broken
  references, stale metadata, unresolvable references, and outside-root
  references. Files with unresolvable references are preserved by basename.
- Every non-dry candidate is revalidated immediately before deletion. A failed
  `unlink` retains its `UploadAsset` row for retry and records one
  `upload.cleanup_failed` audit event. Successful deletion removes metadata and
  records paths and counts in `upload.orphan_cleanup`.
- `POST /api/v1/admin/uploads/cleanup?dry_run=true|false` returns exact
  candidate paths, relative paths, kinds, reasons, and all classification and
  action counts. Dry runs perform no file deletion and no metadata mutation.
- Product deletion remains a soft unpublish; product images are not removed.

The previous `upload_orphans` helper, which treated every file without an
`upload_assets.path` match as deletable, was replaced by the shared
classification and revalidation path.

### Dedicated automated coverage

All tests below are in `tests/test_upload_lifecycle.py` and passed in a single
run of `python -m pytest tests/test_upload_lifecycle.py -q`
(**17 passed, 1 non-fatal deprecation warning**).

| Scenario | Regression test | Result |
|---|---|---|
| Successful replacement removes only the obsolete managed file | `test_successful_replacement_removes_obsolete_managed_file` | Passed; new URL replaces the old one, old file and metadata are gone. |
| Invalid image rejected before mutation | `test_invalid_image_rejected_without_product_mutation` | Passed; 400 response, product images and assets unchanged. |
| Commit failure rolls back and cleans the new file | `test_commit_failure_during_replacement_rolls_back_and_cleans_new_file` | Passed with a monkeypatched commit failure; 500 response, no new file or metadata. |
| Shared image used by another product | `test_shared_image_referenced_by_another_product_is_protected` | Passed; old file and metadata remain while product 3 advances. |
| Shared image repeated in another product's image entries | `test_shared_image_referenced_by_another_image_entry_is_protected` | Passed; duplicate references protect the same file. |
| Referenced legacy file without metadata preserved | `test_legacy_product_image_without_metadata_is_preserved` | Passed; classified as protected legacy, never a candidate. |
| Unreferenced generated file classified correctly | `test_unreferenced_generated_file_is_classified_correctly` | Passed; absolute path, relative path, `legacy` kind, and `unreferenced_generated_file` reason reported without deletion in dry run. |
| Valid managed upload preserved | `test_valid_managed_upload_is_not_classified_as_orphan` | Passed; protected as a managed product reference. |
| True managed orphan detected and deleted | `test_true_managed_orphan_detection` | Passed; dry run identifies `managed` candidate, non-dry run removes file and metadata. |
| Dry-run reports exact files and counts without mutation | `test_dry_run_reports_candidates_without_deleting_or_mutating` | Passed; repeated reports are identical, files/metadata/products unchanged, `deleted_count=0`. |
| Safe non-dry deletion | `test_non_dry_cleanup_deletes_only_confirmed_safe_candidates` | Passed; two unreferenced files deleted, referenced file preserved. |
| Failed deletion keeps retry capability | `test_failed_file_deletion_retains_retry_capability` | Passed with monkeypatched `OSError`; metadata retained and failure audited once. |
| Retry after failed deletion succeeds | `test_retry_after_failed_deletion_succeeds` | Passed; second run deletes file and metadata with no repeated failure audit. |
| Missing file with valid reference reported broken | `test_missing_file_with_valid_product_reference_is_reported_broken` | Passed; broken reference reported, stale metadata not deleted. |
| Traversal and outside-root references rejected | `test_path_traversal_and_outside_root_references_are_ignored` | Passed; outside file and metadata preserved and reported as outside root. |
| Soft unpublish preserves images | `test_soft_unpublish_keeps_product_images` | Passed; status becomes `Unpublished`, image reference and file remain. |
| Cleanup is idempotent | `test_cleanup_is_idempotent` | Passed; second run has zero candidates, zero deletions, and no second cleanup audit. |

Scope remains limited to local file lifecycle safety. Managed-upload cleanup on
hard product deletion is intentionally not implemented because product deletion
is a soft unpublish.

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
| F-030 | FIXED AND VERIFIED for local scope | Reference-safe classification, dry-run reporting, protected shared/legacy files, revalidated non-dry deletion, failed-deletion retry, and 17 dedicated regressions are implemented and passing. |
| F-033 | FIXED AND VERIFIED for local foundation | Consent, deletion, retention, snapshot, provenance, and impression tests passed. |
| F-035 | PARTIALLY FIXED | Expiration, active state, password handling, and throttling verified; MFA/reset/revocation remain. |
| F-036 | DEFERRED WITH JUSTIFICATION | Deployment, monitoring, DR, and external credential controls are production-only. |

All other F-001–F-014 and F-017–F-026, F-031–F-032, and F-034 findings retain
their prior verified dispositions, with their regression evidence preserved in
`tests/test_api.py` and `tests/test_sqlite_concurrency.py`.

## 11. New findings addressed or recorded

| Finding | Root cause | Remediation | Result |
|---|---|---|---|
| N-011 | Money migration assumed nullable comparison values were invalid. | Null-aware Decimal migration conversion. | Isolated retry passed. |
| N-012 | Refund effects were represented only in mutable JSON details. | Added unique `refunds` records and integer amounts. | Cancellation/refund test passed. |
| N-013 | No configurable recommendation retention operation. | Admin cleanup service and audit event. | Privacy/cleanup test passed. |
| N-014 | No reproducible recommendation dataset manifest. | Snapshot model with watermark, criteria, taxonomy, and counts. | Snapshot test passed. |
| N-015 | Upload paths lacked ownership metadata. | `upload_assets` table and orphan cleanup support. | Schema migration passed; invalid-upload and ownership regressions passed. |
| N-016 | Orphan detection relied only on `upload_assets.path`, and failure/shared/dry-run/retry paths lacked dedicated tests. | Added canonical reference resolution, product-reference protection, legacy/traversal classification, exact dry-run reporting, revalidated deletion, retained metadata on failure, and 17 dedicated regressions. | CLOSED AND VERIFIED; no longer blocks local backend READY. |

## 12. Exact commands and results

| Command | Result |
|---|---|
| `python -m pytest tests/test_upload_lifecycle.py -q` | **17 passed**, 1 non-fatal deprecation warning, exit 0 |
| `python -m pytest -q` | **43 passed, 0 failed, 0 skipped**, 5 non-fatal Starlette/httpx deprecation warnings, exit 0 (`43 passed in 26.22s`) |
| `python -m pytest tests/test_sqlite_concurrency.py -q` | 2 passed, 0 failed, exit 0 |
| `python -m compileall -q backend tests scripts start.py` | Passed, exit 0 |
| `python scripts/validate_db_copy.py data/fabrix.db C:/Users/HP/AppData/Local/Temp/opencode/fabrix_final_upload_validation_20261125_1.db` | `integrity_check=ok`, `foreign_key_check=ok`, `foreign_keys=1`, five migrations, exit 0 |
| Active `data/fabrix.db` direct check | `active_integrity ok`, `active_fk []`, `upload_assets 0` |
| `python scripts/verify_assets.py` | `FABRIX OK: 16 pages; 12/12 locally downloaded photos`, exit 0 |

The final full suite includes API security/workflow tests, money conversion,
refund/inventory consistency, consent/deletion/snapshot/impression tests,
SQLite integrity checks, file-backed concurrency tests, and all 17 upload
lifecycle regressions.

## 13. Remaining limitations

1. Compatibility float columns remain for API compatibility; the dedicated
   regression test proves they are non-authoritative.
2. Product deletion is a soft unpublish and does not perform managed-upload
   cleanup; this preserves valid image references by design.
3. MFA, password recovery, token revocation, and distributed throttling are
   not local MVP requirements.
4. Production monitoring, deployment secret rotation, disaster recovery, and
   real payment settlement are not implemented.

## 14. Git history and local version control

Branch: `work/fabrix-final-local-mvp-readiness`. The repository was initialized
locally at the project root; the baseline branch is `main`.

| Commit | Message |
|---|---|
| `5c2000946bc439ac5311c43a036a5678acd7f23f` | `chore(git): establish FABRIX local baseline` |
| `6b62bc8379c50d837f3d51bb2482a3786963165e` | `perf(catalog): verify database-side filtering` |
| `ddb7ce179ae4f03b3f569a03ddc179902eeba14a` | `fix(uploads): complete managed replacement lifecycle` |
| `7e85c32791f2497e8b0b0670efd7c4107ad731f6` | `docs(readiness): record local MVP approval evidence` |
| `8a2c3a1d61fcecd01f2c4822b9d1a5a67e1e867a` | `fix(uploads): make cleanup reference-safe and retryable` |

Implementation and tests were committed first; the final report update is a
separate local commit. This report intentionally does not record its own commit
hash. Final Git status after both commits is clean. No remote is configured
(`git remote -v` is empty). `git ls-files` contains no active SQLite database,
database backup, uploaded file, `.env` secret, credential, or
virtual-environment artifact. No push, force push, publish, tag, release, or
deployment was performed.

## 15. Final readiness decisions

### A. Local Backend Security and Integrity

**READY for the local MVP**

The upload lifecycle gap that previously blocked this decision is closed:
cleanup now protects referenced legacy and shared files, rejects traversal and
outside-root references, reports exact dry-run candidates without mutation,
revalidates candidates before deletion, retains metadata after failed deletion
for retry, and is covered by 17 dedicated passing regressions. The full 43-test
suite, concurrency tests, compilation, database validation, and asset
verification also pass. This decision is scoped to the local MVP; it does not
claim production hardening.

### B. Recommendation Data Foundation

**READY**

The recommendation event taxonomy, server-only purchase events, stable IDs,
consent filtering, user deletion, configurable retention, snapshot lineage,
eligibility checks, and impression acknowledgment remain supported by the
passing tests.

### C. Recommendation Implementation

**APPROVED TO START**

Approval requires both a ready local backend and a ready recommendation data
foundation. Both conditions are now met. This approves local implementation
work only; it does not deploy, publish, or change payment, authentication, or
recommendation behavior.

### D. Production Readiness

**NOT READY**

Production monitoring, deployment controls, MFA, distributed abuse protection,
disaster recovery, real payment reconciliation, and operational secret
management are not implemented. These remain production-only requirements and
are not the reason the local backend decision changed.
