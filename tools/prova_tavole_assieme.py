"""Prova (03/11): le tavole di un assieme vero (copiato in una cartella temporanea, l'originale non si tocca) con
tutte le tavole dei pezzi, rese come immagini; e il «Prepara» dell'assieme (DXF di tutti i pezzi in lamiera).

    python tools/prova_tavole_assieme.py CARTELLA_ASSIEME CARTELLA_FOTO
"""
import shutil, sys, tempfile, time
from pathlib import Path
W = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(W))
from playwright.sync_api import sync_playwright
from app.service import Service
SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp()) / SRC.name
shutil.copytree(SRC, tmp, ignore=shutil.ignore_patterns('*.pdf', '*.step', '*.autosave'))
asm = next(p for p in tmp.glob('*.steelcad-asm') if len(p.read_bytes()) > 1000)
s = Service()
t = time.time(); r = s.open(str(asm)); print('apri', r.get('ok'), r.get('message'), round(time.time() - t, 1), 's', flush=True)
t = time.time(); prev = s.drawing_preview(None, True); print('tavole', prev.get('ok'), prev.get('message'), len(prev.get('sheets') or []), round(time.time() - t, 1), 's', flush=True)
info = s.prepara_info(); print('prepara', [(v['id'], v['si'], v['file']) for v in info['voci']])
t = time.time(); r = s.prepara(str(tmp / 'uscita'), [v['id'] for v in info['voci'] if v['si'] and v['id'] != 'step'], None)
print('prepara fatto', r.get('ok'), r.get('message'), round(time.time() - t, 1), 's')
for x in sorted((tmp / 'uscita').rglob('*')):
    print('  ', x.relative_to(tmp / 'uscita'))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for i, sh in enumerate(prev.get('sheets') or [], 1):
        pg = b.new_page(viewport={'width': 1800, 'height': 1273})
        pg.set_content('<html><body style="margin:0;background:#fff">' + sh['svg'].replace('<svg', '<svg style="width:1800px;height:auto"', 1) + '</body></html>')
        pg.screenshot(path=str(OUT / f'tav{i:02d}.png'), full_page=True); pg.close()
        print(i, sh['title'])
    b.close()
