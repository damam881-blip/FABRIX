# FABRIX — marketplace prototype

FABRIX is a local-first handmade marketplace prototype with a complete static frontend and a FastAPI + SQLite backend. The browser uses the API when it is running and falls back to the original `localStorage` demo when it is not, so opening a page directly from disk still works.

## Developer setup (fresh clone)

Tested with Python 3.12.10 and Git 2.54.0 on Windows. Use Python 3.12 for the
closest match to the verified environment. Git is required only to clone the
repository; the application itself does not need Git at runtime.

The exact three-command quick start, after Python and Git are available and the
backend packages are already installed, is:

```bash
git clone https://github.com/damam881-blip/FABRIX.git
cd FABRIX
python start.py
```

A recommended isolated setup on Windows PowerShell is:

```powershell
git clone https://github.com/damam881-blip/FABRIX.git
cd FABRIX
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python start.py
```

Equivalent macOS/Linux commands:

```bash
git clone https://github.com/damam881-blip/FABRIX.git
cd FABRIX
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python start.py
```

`start.py` checks the bundled photos and installs runtime dependencies from
`requirements.txt` only if imports fail. It does not install
`requirements-dev.txt`, which is needed for tests. The product and editorial
photos are committed, so no download is required for startup; the download
scripts only refresh missing files. A new `data/fabrix.db` is created and seeded
automatically on first startup. Seeding is idempotent and does not duplicate
demo users or products on later runs.

`start.py` seeds demo data and starts:

| Service | URL | Purpose |
| --- | --- | --- |
| FastAPI + static site | `http://127.0.0.1:8000/` | Recommended. API, docs, and the same pages in one server |
| Legacy static server | `http://127.0.0.1:5500/` | Existing browser tests; automatically detects the API on port 8000 |
| API docs | `http://127.0.0.1:8000/docs` | Swagger UI |
| Health check | `http://127.0.0.1:8000/health` | `{"status":"ok"}` |

The API prefix is `/api/v1`. Ports can be changed with `FABRIX_API_PORT` and `FABRIX_STATIC_PORT`.

### Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Buyer | `buyer@example.com` | `Demo12345` |
| Artisan | `artisan@example.com` | `Demo12345` |
| Admin | `admin@example.com` | `Admin12345` |

The artisan account owns the approved textile studio **North Loop Knits**. Admin actions (store approval, product blocking, delivery confirmation, review-report resolution) require the admin account.

Public registration cannot create administrator accounts. For a local
administrator bootstrap, set `FABRIX_ADMIN_BOOTSTRAP_SECRET` and run:

```powershell
python scripts/create_admin.py --email admin2@example.com --name "FABRIX Admin"
```

The command prompts for the bootstrap secret and password; credentials are
not accepted as command-line arguments.

## Inspect the database

The local database is `data/fabrix.db` (SQLite). A readable report is built in:

```powershell
python scripts/inspect_db.py             # table counts and key records
python scripts/inspect_db.py --table orders
python scripts/inspect_db.py --full      # every row of every table
```

The report never prints password hashes. You can also open `data/fabrix.db` with any SQLite viewer, or browse the API at `/docs`.

## What the backend owns

When the API is reachable, the frontend delegates to it for:

- registration, password login, JWT bearer auth, profile, addresses, and notifications
- the published catalog, product drafts, seller publishing, and moderation
- server-side cart and favorites, with local state migrated on first API sign-in
- 15-minute stock reservations and atomic sandbox checkout
- parent orders, per-seller orders, seller fulfillment, admin delivery confirmation, and cancellations
- verified reviews (delivered order items only), reports, and admin moderation
- consent-aware, eligibility-filtered recommendations with event deduplication
- audit logs for lifecycle and moderation decisions

Payments are sandbox-only. No external payment provider or remote image service is contacted at runtime.

## API surface

High-level endpoints (all under `/api/v1`):

- `/auth` — register, login, current user, logout
- `/users` — profile, addresses, notifications
- `/products` — catalog, featured, seller listings, drafts, admin moderation
- `/favorites`, `/cart`, `/reservations` — shopping state
- `/orders` — checkout, buyer orders, seller orders, seller/admin status changes, payments
- `/seller`, `/admin` — store lifecycle, admin stats, audit log, products and seller-order lists
- `/reviews`, `/admin/reviews` — reviews and moderation
- `/recommendations` — events and personalized/general discovery
- `/newsletter` — demo newsletter signup

The OpenAPI schema at `/docs` is the authoritative request/response reference.

## Frontend fallback

`js/api-bridge.js` probes the local API on `localhost`/`127.0.0.1` (or when `?api=1` is present). Pages can await `window.FabrixAPI.ready` before their first render; it resolves after API detection, catalog loading, and token-based state hydration, or immediately in fallback mode. If the API is unavailable, all original browser-only flows remain active:

- `fabrix-cart` — `{ "<productId>": quantity }`
- `fabrix-favorites` — array of product IDs
- `fabrix2-demo-v6` — account, orders, store, drafts, reviews, and preferences
- `fabrix-account-states-v1` and `fabrix-demo-profiles-v1` — per-email demo profiles

With the API active, the bridge keeps those keys in sync as a cache and sends cart/favorite changes and recommendation events to the server. On first API sign-in, any existing local cart and favorites are migrated to the authenticated account.

## Photos

The 12 product photos and 12 editorial photos are bundled under `assets/photos/`, with local SVG fallbacks kept in `assets/products/`. `css/local-photos.css` and `css/editorial-photos.css` reference them directly, so the site runs without a download step. The scripts only refresh missing or replaced photos:

```powershell
python scripts/download_photos.py
python scripts/download_editorial_photos.py
python scripts/verify_assets.py
```

Downloads require internet once. Every source photo in the registry is unique; if a source is unavailable, the committed fallback remains. Zip the whole `FABRIX` folder to share your exact local state, including downloaded JPEGs.

## Tests and verification

Install test dependencies once, then run database-dependent suites sequentially:

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q backend tests scripts start.py
python scripts/verify_assets.py
python -m pytest -q
python -m pytest tests/test_upload_lifecycle.py -q
python -m pytest tests/test_sqlite_concurrency.py -q
python scripts/validate_db_copy.py data/fabrix.db "$env:TEMP/fabrix-validation.db"
```

macOS/Linux equivalents use `python3` and a temporary path such as
`/tmp/fabrix-validation.db`. Do not run two pytest processes at the same time;
they share a temporary test database. `tests/test_api.py` covers
registration/login, seeded catalog order, frontend page serving, favorites,
cart sync, reservation, checkout and idempotency, seller transitions, verified
reviews, recommendations, admin stats, and ownership scoping.
`tests/test_upload_lifecycle.py` covers reference-safe upload replacement and
cleanup. `tests/test_sqlite_concurrency.py` covers SQLite write behavior.

## Local data and configuration

- SQLite database: `data/fabrix.db` (created/seeded automatically on first startup; ignored by Git)
- Configuration: `.env` (copy `.env.example`); override database URL, secret key, token lifetime, and allowed frontend origins there
- The schema uses SQLAlchemy, so the same models can be pointed at MySQL/PostgreSQL later without rewriting the routers

To keep a fresh clone completely isolated from an existing database, set an
absolute SQLite URL before starting the app:

```powershell
$env:FABRIX_DATABASE_URL = 'sqlite:///C:/path/to/fabrix-dev.db'
python start.py
```

On macOS/Linux:

```bash
export FABRIX_DATABASE_URL='sqlite:////tmp/fabrix-dev.db'
python start.py
```

Stop the app by pressing `Ctrl+C` in the terminal running `start.py`; it
terminates both the API and the legacy static server.

The demo credentials above are local-only demonstration accounts and are not
production credentials. Do not put real secrets in `.env` and commit it; only
`.env.example` is tracked.

## Notes

- The 12 seeded products follow the original curated frontend order: IDs `[5, 6, 1, 2, 3, 4, 7, 8, 9, 10, 11, 12]`.
- Product states: `Draft`, `Published`, `Unpublished`, `Blocked`.
- Store states: `Draft`, `Pending`, `Approved`, `Changes Requested`, `Suspended`.
- Seller-order states: `Awaiting Processing`, `Processing`, `Shipped`, `Delivered`, `Cancelled`.
- One identity can shop and sell; selling requires an approved store, but it does not disable buyer features.
- Minor Lighthouse color-contrast and label suggestions from the static prototype are accepted for this prototype.
- See `PHOTO_SETUP.md` and `README_UPDATE.md` for photo-history details.
