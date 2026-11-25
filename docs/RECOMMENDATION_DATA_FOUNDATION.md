# FABRIX Recommendation Data Foundation

## Current event contract

The API accepts controlled interaction types:

- `PRODUCT_VIEW`
- `FAVORITE_ADD`
- `FAVORITE_REMOVE`
- `CART_ADD`
- `CART_REMOVE`
- `RECOMMENDATION_IMPRESSION`
- `RECOMMENDATION_CLICK`
- `DISMISS`

Purchase events are not accepted from clients. Checkout creates trusted
server-side purchase events after order records are built in the same
database transaction.

## Event fields

Events now preserve:

- Stable event ID.
- Event type.
- Product ID.
- Optional authenticated user ID.
- Optional session ID.
- Occurred time.
- Received time.
- Source context.
- Recommendation request ID.
- Model version.
- Display position.
- Consent snapshot.
- Weighted signal.

## Serving eligibility

Recommendations use the same product eligibility predicate as cart,
reservation, and checkout flows. Products must be published, in stock, owned
by an authoritative seller, and associated with an approved store.

## Current limitations

- Actual client visibility acknowledgment for recommendation impressions is not
  yet implemented.
- Dataset snapshots and model lineage are not yet implemented.
- User-data deletion and training-dataset exclusion workflows are not yet
  implemented.
- Seller/admin behavioral signal separation needs additional source validation.
- Offline train/validation/test export tooling is not yet implemented.

Recommendation model development should wait until these limitations are
addressed.
