# FABRIX Backend Remediation Final Report

> Historical status notice: findings below reflect this report's original pass.
> Later verified work resolved the upload lifecycle and recommendation
> deletion/retention/impression gaps. See
> `docs/FABRIX_FINAL_BLOCKERS_REMEDIATION_REPORT.md` and
> `docs/RECOMMENDATION_DATA_FOUNDATION.md` for current status.

## Scope and safety

This report covers the authorized backend/database remediation pass. Work was
performed locally only. No deployment, remote push, real payment, credential
exposure, or destructive database reset was performed.

The active database was backed up before changes:

`data/backups/fabrix_before_remediation_20261125_185856.db`

The backup passed SQLite `PRAGMA integrity_check` with result `ok`. A separate
database copy was used for migration validation and also passed integrity
checking.

## Outcome

The highest-risk authorization, seller-ownership, idempotency, eligibility,
foreign-key, reservation, review, upload, and recommendation-event issues were
remediated. The marketplace remains sandbox-only. Full production readiness is
not claimed because fixed-precision money migration, a full versioned migration
tool, production payment reconciliation, and several authentication controls
remain follow-up work.

## Verification

- `python -m pytest -q`: **14 passed**
- `python -m compileall -q backend scripts start.py`: passed
- JavaScript syntax checks for modified files: passed
- Migration-copy `PRAGMA integrity_check`: **ok**
- Migration-copy foreign keys: **enabled**
- Runtime health endpoint: **ok**
- Runtime catalog: **12 products**
- Runtime OpenAPI paths: **53**

## Finding reconciliation

| Finding | Status | Resolution / remaining action |
|---|---|---|
| F-001 | Remediated | Public registration cannot create Admin accounts. |
| F-002 | Remediated | Added interactive out-of-band Admin provisioning via `scripts/create_admin.py`. |
| F-003 | Remediated | Checkout idempotency is scoped to authenticated user and operation. |
| F-004 | Remediated | Idempotency payload fingerprinting rejects reuse with a different request. |
| F-005 | Remediated | Seller-order authorization uses stable seller user IDs. |
| F-006 | Remediated | Seller-order ownership is backfilled from authoritative product ownership. |
| F-007 | Remediated | Product/cart/checkout/recommendation eligibility requires an approved store. |
| F-008 | Remediated | Public artisan registration creates a Draft store and no selling capability. |
| F-009 | Remediated | Seller product updates cannot mass-assign protected metadata. |
| F-010 | Remediated | Checkout stock decrements use conditional database updates. |
| F-011 | Remediated | Reservation allocation, release, expiry, and consumption use conditional state updates. |
| F-012 | Remediated | Duplicate product lines and reservation tokens are aggregated. |
| F-013 | Remediated | Seller order ownership is represented by stable identifiers. |
| F-014 | Remediated | Parent order status is derived from seller-order state rather than freely assigned. |
| F-015 | Remediated | Cancellation restores stock for cancelled seller-order items. |
| F-016 | Partially remediated | Sandbox refund/partial-refund adjustments are recorded; external reconciliation and a complete payment state machine remain. |
| F-017 | Remediated | Checkout rejects non-sandbox payment methods. |
| F-018 | Remediated | Shipping contact email must match the authenticated account. |
| F-019 | Remediated | SQLite foreign keys are enabled at connection level. |
| F-020 | Partially remediated | Migration bridge and migration records were added; a full versioned production migration framework remains. |
| F-021 | Partially remediated | Existing ownership is backfilled where authoritative product/order links exist; ambiguous historical mappings are not invented. |
| F-022 | Remediated | Review uniqueness is enforced per order item. |
| F-023 | Remediated | Review eligibility requires a delivered seller order. |
| F-024 | Remediated | Sellers cannot review their own products. |
| F-025 | Remediated | Review rating bounds are enforced in the model/database contract. |
| F-026 | Remediated | Product uploads enforce size and basic JPEG/PNG/WebP signatures. |
| F-027 | Partially remediated | Audit coverage exists for core order/store/review actions; comprehensive immutable audit coverage remains follow-up work. |
| F-028 | Open follow-up | Money fields still use floating-point storage; fixed-precision migration requires a reviewed conversion plan. |
| F-029 | Open follow-up | Broad pagination and query optimization across all collection endpoints remain. |
| F-030 | Open at this pass; later fixed | Upload ownership tracking and orphan cleanup were open; later verified work made replacement and cleanup reference-safe and retryable. |
| F-031 | Remediated | Recommendation event types are controlled and client purchase events are rejected. |
| F-032 | Remediated | Server-side purchase events include provenance and consent snapshots. |
| F-033 | Partially remediated at this pass | Recommendation events now carry timestamps, source, request, model, position, and consent context; deletion/retention were later implemented. |
| F-034 | Partially remediated at this pass | Recommendation serving filters out ineligible products; API-level impression acknowledgment and basic dataset lineage were later implemented. |
| F-035 | Open follow-up | MFA, rate limiting, password recovery, and privileged-session controls remain. |
| F-036 | Open follow-up | Production operational controls, monitoring, backups/restore drills, and deployment-specific secrets management remain. |

## Data preservation

The active local database was retained. Existing orders, reviews, audit data,
reservations, and seeded catalog records were preserved. Catalog products now
have authoritative seller IDs, and historical seller orders that had
deterministic product ownership were backfilled. No ambiguous ownership was
fabricated.

## Recommendation readiness decision

Recommendation algorithms remain deferred. At this pass the event schema and
eligibility predicate were materially safer but retention/deletion, dataset
lineage, and impression acknowledgment were still open. Those controls were
implemented in later verified passes; current status and remaining future work
are documented in `docs/RECOMMENDATION_DATA_FOUNDATION.md`.

## Next approved work

1. Introduce a fully versioned migration tool and review all historical
   ownership mappings.
2. Convert monetary fields to fixed precision using a copy, reconciliation,
   and explicit approval process.
3. Complete payment state transitions, reconciliation, and refund workflows.
4. Add concurrency tests on supported database engines.
5. Complete authentication, rate limiting, pagination, upload lifecycle, and
   recommendation privacy controls.
