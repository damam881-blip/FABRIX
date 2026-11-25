#!/usr/bin/env python3
"""One-time local photo downloader for FABRIX demo. Requires internet on this machine.
Images are locally saved and never fetched from the website during page load.
No third-party packages required. Sources tracked in assets/photos/photo-sources.json.
"""
from pathlib import Path
import urllib.request,urllib.error,json,sys
ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'assets/photos/photo-sources.json'
DEST=ROOT/'assets/photos/products'
CSS=ROOT/'css/local-photos.css'
DEST.mkdir(parents=True,exist_ok=True)

def verify(path):
    try:
        data=path.read_bytes()
        return len(data)>8000 and (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n') or data[:4]==b'RIFF' and data[8:12]==b'WEBP')
    except OSError: return False

def build_css(rows):
    lines=['/* Generated local product photographs. Keep this file after fabrix-v8.css. */']
    for row in rows:
        n=row['product_id'];file=DEST/f'product-{n:02d}.jpg'
        if not verify(file): continue
        rel=f'../assets/photos/products/product-{n:02d}.jpg'
        lines.append(f'.product-visual[href="product.html?id={n}"]{{background-image:url("{rel}")!important;}}')
        lines.append(f'.drawer-thumb[data-product-id="{n}"],.cart-thumb[data-product-id="{n}"],.saved-thumb[data-product-id="{n}"]{{background-image:url("{rel}")!important;background-size:cover!important;background-position:center!important;}}')
        lines.append(f'body[data-product-id="{n}"] .detail-visual,body[data-product-id="{n}"] .detail-thumbnails .thumb{{background-image:url("{rel}")!important;}}')
    CSS.write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    rows=json.loads(REGISTRY.read_text(encoding='utf-8'))
    ok=0
    for row in rows:
        n=row['product_id']; target=DEST/f'product-{n:02d}.jpg'
        if verify(target):
            print(f'[{n:02d}] Already downloaded: {target.name}');ok+=1;continue
        candidates=[row['photo_id'], *row.get('alternate_photo_ids',[])]
        success=False
        for pid in candidates:
            url=f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=900"
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (FABRIX educational demo)'})
                with urllib.request.urlopen(req,timeout=20) as resp:
                    data=resp.read(6_000_000)
                    typ=resp.headers.get('Content-Type','')
                if 'image/' not in typ.lower() or len(data)<8000 or not data.startswith(b'\xff\xd8\xff'):
                    raise ValueError('Server did not return a valid JPEG photo')
                target.write_bytes(data)
                ok+=1;success=True
                print(f'    OK ({len(data)//1024} KB, Pexels {pid})')
                break
            except (urllib.error.URLError,TimeoutError,ValueError,OSError) as ex:
                print(f'    Source {pid} unavailable: {ex}')
        if not success:print('    SKIPPED: existing SVG remains visible')
        build_css(rows)
    build_css(rows)
    print(f'\nLocal photos: {ok}/{len(rows)}. CSS generated at css/local-photos.css')
    print('Share the WHOLE FABRIX folder (including assets/photos) with your teammate.')
    if ok!=len(rows):
        print('If a photo was unavailable, download a licensed JPEG manually and save it as product-NN.jpg, then rerun.')
    return 0 if ok else 1
if __name__=='__main__':sys.exit(main())
