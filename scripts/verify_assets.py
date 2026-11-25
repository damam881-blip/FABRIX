from pathlib import Path
import re,json,sys
root=Path(__file__).resolve().parents[1]
items=json.loads((root/'assets/photos/photo-sources.json').read_text(encoding='utf8'))
css=(root/'css/local-photos.css').read_text(encoding='utf8')
valid=0
for p in items:
 n=p['product_id'];f=root/f'assets/photos/products/product-{n:02d}.jpg'
 if f.exists() and f.read_bytes().startswith(b'\xff\xd8\xff') and len(f.read_bytes())>8000:
  valid+=1
  assert f'product-{n:02d}.jpg' in css, f'Missing CSS mapping for {n}'
 else:
  print('Fallback SVG:',n,p['product_name'])
assert all('css/local-photos.css' in h.read_text(encoding='utf8') for h in root.glob('*.html'))
print(f'FABRIX OK: {len(list(root.glob("*.html")))} pages; {valid}/{len(items)} locally downloaded photos')
