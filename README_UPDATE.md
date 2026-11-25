# FABRIX v8.3 — Editorial Photos + Customer / Artisan Account UX

This update is designed to **merge over your existing FABRIX folder** without removing `assets/photos/products/` (your 12 already-downloaded product photos).

## Apply safely
1. Make a backup of your current FABRIX folder.
2. Copy the contents of this update's `FABRIX/` into your current FABRIX folder. **Merge folders; replace files when Windows asks. Do not delete your original folder.**
3. In VS Code terminal from the FABRIX root run:
   ```powershell
   python scripts/download_editorial_photos.py
   ```
4. Verify that `assets/photos/makers/maker-workshop.jpg` and the 4 images in `assets/photos/categories/` exist.
5. Open `index.html` with Live Server, hard refresh Chrome with Ctrl+Shift+R.
6. Open `auth.html` and test Create account (Shop handmade / Sell my craft), then Sign in using the same email. Passwords are not requested because **this is only a frontend simulation**.

Sources are documented in `assets/photos/editorial-sources.json` (Pexels). Demo images do not represent real inventory or a specific artisan. The website uses relative asset paths and does not access the photo hosting service at runtime.

## Functional rules
- Customer / artisan are two **entry flows**, not two incompatible identities. An artisan retains buyer privileges.
- Artisan create-account captures studio name and story, stores a Draft application, and requires admin approval before publishing.
- Existing buyer demo can choose seller flow, enabling a Draft artisan workspace on the same email.
- This is **not authentication**. Browser localStorage is not a safe user database or permissions system; the PHP/MySQL backend must implement password handling, sessions and authorization.
- Existing v8 products, shopping cart and favorites remain unchanged in this patch.

## Offline sharing
Once photos download, zip the **whole merged FABRIX folder** including `assets/photos`. Your teammate does not need the download scripts or external network at runtime.
