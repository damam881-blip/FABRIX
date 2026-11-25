# FABRIX Backend Remediation Progress

## Execution status

Started after the read-only backend/database audit. No Git repository is
present in this workspace, so a remediation branch could not be created.
Existing work was preserved.

## Safety baseline

- Timestamped backup created under `data/backups/` before database changes.
- Backup integrity check: `PRAGMA integrity_check` returned `ok`.
- Existing test baseline: `7 passed`.
- Active local database was retained; no destructive reset was performed.

## Completed implementation tasks

### P0

- Public registration no longer accepts `admin`.
- Added `scripts/create_admin.py` for interactive, out-of-band administrator
  provisioning.
- Added SQLite connection-level foreign-key enforcement.
- Added an idempotency migration with user/operation/request-hash fields.
- Checkout idempotency is now user-scoped and payload-bound.
- Artisan registration creates Draft stores and does not grant selling
  capability.
- Store approval is required for product publication.
- Product/catalog/cart/reservation/checkout/recommendation eligibility now
  checks approved store ownership.

### P1

- Reservation allocation uses conditional atomic updates.
- Reservation release/expiration/consumption uses conditional state changes.
- Duplicate checkout product lines and reservation tokens are aggregated.
- Seller orders receive stable seller ownership IDs.
- Seller fulfillment authorization uses seller IDs rather than display names.
- Cancellation restores product stock and records sandbox refund adjustments.
- Seller product updates cannot change protected metadata fields.
- Self-review of an artisan's own product is rejected.
- Product uploads validate basic image signatures.
- Purchase recommendation events are generated from committed checkout state.
- Client-submitted purchase events are rejected.
- Recommendation events now require controlled event types.

## Tests added

- Public admin registration rejection.
- Cross-user idempotency isolation.
- Idempotency payload conflict.
- Seller protected-field rejection.
- Client purchase-event rejection.
- Artisan self-review rejection.
- Suspended-store purchase/recommendation exclusion.

## Current verification

- `python -m pytest tests/test_api.py -q`: 13 passed.
- `python -m compileall -q backend scripts start.py`: passed.
- JavaScript syntax checks: passed for modified files.
- Existing local database migration and seed completed successfully.

## Remaining work

- Replace the dependency-free migration bridge with a fully versioned
  production migration workflow.
- Complete fixed-precision monetary migration.
- Complete explicit payment state machine and reconciliation workflow.
- Expand cancellation and concurrency coverage.
- Add pagination/query-side filtering across all large collections.
- Complete upload tracking/orphan cleanup.
- Add recommendation impression/click contracts and privacy lineage.
- Add MFA, rate limiting, password recovery, and privileged session controls.
- Produce final finding-by-finding remediation reconciliation after the full
  regression suite.
