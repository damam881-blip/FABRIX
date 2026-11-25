# FABRIX v8.4 — Full project

## Start
1. Extract the ZIP into a **new** folder; do not overwrite your earlier v8.3 folder.
2. Open `FABRIX` in VS Code; run Live Server on `index.html`.
3. Open Chrome at `http://127.0.0.1:5500/`.

## Get local licensed editorial and product photography
The ZIP does **not** contain downloaded real photographs. With internet available on your Windows laptop, open terminal in `FABRIX` and run:

```powershell
python scripts/download_editorial_photos.py
python scripts/download_photos.py
python scripts/verify_assets.py
```

If the photo download returns fewer than 5 editorial and 12 product images, you may retry, or obtain licensed replacement JPGs and save them under `assets/photos/makers/maker-workshop.jpg`, `assets/photos/categories/ceramics.jpg`, `textiles.jpg`, `jewelry.jpg`, `home-objects.jpg`, or `assets/photos/products/product-05.jpg`. Then rerun the corresponding script to regenerate CSS.

**No web images are fetched by the website at page load.** Once downloaded, copy/share the complete FABRIX folder. Images are editorial placeholders, not photographs of the actual goods/sellers named in the demo.

## Test account switching
- Open `auth.html?mode=register&role=customer`. Register buyer with email `buyer-demo@example.com`.
- Open Account → **Sign out** (or use header Sign out).
- Open `auth.html?mode=register&role=artisan`. Register seller with a *different* example email; add studio name and story.
- Sign out and sign in again with either example email, choosing the matching experience.
- Both routes are local browser simulations, with no passwords or secure identity checks. A single account may also gain artisan capability under the approved project rules.

Don't use real credentials for this prototype. Browser storage is not a secure user database. Payments, order operations and Admin permissions remain demos pending PHP/MySQL backend.
