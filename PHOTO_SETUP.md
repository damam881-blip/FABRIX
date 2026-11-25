# FABRIX portable product photos

The project originally contains 12 locally stored SVG illustrations. The new optional photo workflow adds real **stock photography** as illustrative demo media, not genuine photos of products sold by the named sample artisans.

## Setup on Windows

1. Open the `FABRIX` folder in VS Code. Ensure Python is installed.
2. Connect to the Internet ONCE and run `python scripts/download_photos.py` in the FABRIX terminal.
3. Run `python scripts/verify_assets.py` to verify the downloaded images and CSS rules.
4. Open `index.html` using Live Server and review Marketplace, Product Details, Favorites and Cart.
5. Turn off Internet and reload pages. Images should still be available.
6. ZIP the **entire FABRIX directory**, including `assets/photos/products/` and `css/local-photos.css`, to share with teammates.

The script downloads JPEG files from Pexels and writes CSS overrides only for successful downloads. Missing files keep the pre-existing local SVG artwork. To replace any product photo manually, save a real JPEG as `assets/photos/products/product-01.jpg` (01-12) and rerun the downloader to regenerate the mappings.

**Caution:** Photos are generic stock illustrations. Some are only a category or craft-style match, not the named item. Do not claim they depict the actual artisan's inventory. Review the source URLs and Pexels license before public use. Individual photo provenance is recorded in `assets/photos/photo-sources.json`.

**Portability:** HTML, CSS and JavaScript use relative paths. No photo fetch is performed in browser. Google Fonts are still remote, however, so offline font rendering may use local fallbacks; to make *all* design assets completely offline you'd also bundle appropriately licensed fonts.

**If downloads fail:** Your browser or network may block images. Open the photo source page shown in `photo-sources.json`, download with its license, and save the JPEG with the matching local filename. Then rerun the script.
