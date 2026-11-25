#!/usr/bin/env python3
"""Fetch licensed Pexels stock photos to local assets and write CSS for successfully saved files.
Keep the files for offline sharing; product images are managed separately.
"""
from pathlib import Path
import json,urllib.request,urllib.error,sys
ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'assets/photos/editorial-sources.json'
OUT=ROOT/'css/editorial-photos.css'
ROWS=json.loads(REG.read_text(encoding='utf-8'))

def valid(path):
 try:
  x=path.read_bytes()
  return len(x)>8000 and x[:3]==b'\xff\xd8\xff'
 except OSError:return False

def generate():
 css=['/* Generated only for editorial photos actually present on disk. */']
 for row in ROWS:
  name=row['name'];path=ROOT/'assets/photos'/row['folder']/(name+'.jpg')
  if not valid(path):continue
  url=f'../assets/photos/{row["folder"]}/{name}.jpg'
  if name=='maker-workshop':
   css.append(f'.maker-photo{{background-image:linear-gradient(180deg,#0000,#0002),url("{url}")!important;background-size:cover!important;background-position:center!important}}.maker-photo span{{display:none}}')
  elif name in ('ceramics','textiles','jewelry','home-objects'):
   idx={'ceramics':1,'textiles':2,'jewelry':3,'home-objects':4}[name]
   css.append(f'.category-card:nth-child({idx}){{background-image:linear-gradient(180deg,#fff0 45%,#f8f5eeed 100%),url("{url}")!important;background-size:cover!important;background-position:center!important}}.category-card:nth-child({idx}) .category-symbol{{display:none}}')
 # Hero uses its own distinct photographs (no duplicates with category cards).
 hero_poster=ROOT/'assets/photos/heroes/hero-poster.jpg'
 if valid(hero_poster):
  css.append('.hero-art .art-poster{background:linear-gradient(180deg,#0000,#00000013),url("../assets/photos/heroes/hero-poster.jpg") center/cover no-repeat!important}.hero-art .art-poster .vase,.hero-art .art-poster .vase-mouth{display:none!important}.hero-art .handwritten{background:#f9f5eecc;border-radius:5px;padding:8px 12px}')
 hero_small=ROOT/'assets/photos/heroes/hero-small.jpg'
 if valid(hero_small):
  css.append('.hero-art .art-small{background:url("../assets/photos/heroes/hero-small.jpg") center/cover no-repeat!important}.hero-art .ring-shape{display:none!important}')
 # Artisan page uses its own distinct photographs (no placeholders).
 artisan_studio=ROOT/'assets/photos/artisan/artisan-studio.jpg'
 if valid(artisan_studio):
  css.append('.studio-image{background-image:url("../assets/photos/artisan/artisan-studio.jpg")!important;background-size:cover!important;background-position:center!important}.studio-image .studio-vase{display:none!important}.studio-image-caption{background:rgba(248,243,234,.72);padding:6px 10px;border-radius:6px}')
 artisan_story=ROOT/'assets/photos/artisan/artisan-story.jpg'
 if valid(artisan_story):
  css.append('.story-visual-art{background-image:url("../assets/photos/artisan/artisan-story.jpg")!important;background-size:cover!important;background-position:center!important}.story-visual-art .story-vessel{display:none!important}')
 process_material=ROOT/'assets/photos/artisan/process-material.jpg'
 if valid(process_material):
  css.append('.process-art.clay-art{background-image:url("../assets/photos/artisan/process-material.jpg")!important;background-size:cover!important;background-position:center!important}.process-art.clay-art:after{display:none!important}')
 process_form=ROOT/'assets/photos/artisan/process-form.jpg'
 if valid(process_form):
  css.append('.process-art.wheel-art{background-image:url("../assets/photos/artisan/process-form.jpg")!important;background-size:cover!important;background-position:center!important}.process-art.wheel-art:after{display:none!important}')
 process_finish=ROOT/'assets/photos/artisan/process-finish.jpg'
 if valid(process_finish):
  css.append('.process-art.glaze-art{background-image:url("../assets/photos/artisan/process-finish.jpg")!important;background-size:cover!important;background-position:center!important}.process-art.glaze-art:after{display:none!important}')
 OUT.write_text('\n'.join(css)+'\n',encoding='utf-8')

ok=0
for row in ROWS:
 name=row['name']; dest=ROOT/'assets/photos'/row['folder']/(name+'.jpg');dest.parent.mkdir(parents=True,exist_ok=True)
 if valid(dest):print(name+': already available');ok+=1;continue
 pid=row['photo_id'];url=f'https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&w=1400'
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 FABRIX educational preview'})
  with urllib.request.urlopen(req,timeout=25) as res:
   content=res.read(8_000_000)
   mime=res.headers.get('Content-Type','')
  if 'image/' not in mime.lower() or len(content)<8000 or content[:3]!=b'\xff\xd8\xff':raise ValueError('invalid JPEG')
  dest.write_bytes(content);ok+=1;print(name+': saved')
 except (urllib.error.URLError,ValueError,TimeoutError,OSError) as e:print(name+': not downloaded ('+str(e)+')')
 generate()
generate();print(f'{ok}/{len(ROWS)} editorial photos available locally; stylesheet updated')
sys.exit(0 if ok else 1)
