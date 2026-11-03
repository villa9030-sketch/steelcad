"""Prova (03/11): «Prepara per l'officina» di un assieme vero (copiato in una cartella temporanea): la voce «Per il
laser» con i DXF di tutti i pezzi in lamiera, la conferma coi file.

    python tools/prova_ui_prepara_assieme.py CARTELLA_ASSIEME CARTELLA_FOTO [porta]
"""
import os, shutil, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[3] if len(sys.argv) > 3 else '5266'
tmp = Path(tempfile.mkdtemp())
cart = tmp / SRC.name
shutil.copytree(SRC, cart, ignore=shutil.ignore_patterns('*.pdf', '*.step', '*.autosave'))
asm = next(p for p in cart.glob('*.steelcad-asm') if len(p.read_bytes()) > 1000)
srv = subprocess.Popen([PY, str(W / 'app/dev_server.py'), '--porta', PORTA, '--cartella', str(tmp)], cwd=str(W),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp)))
while not srv.stdout.readline().startswith(b'http'): pass
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        print('apri', api('open_path', str(asm)).get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000); time.sleep(3)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.click('#b-prepara'); time.sleep(3)
        pg.screenshot(path=str(OUT / 'asm_prepara.png'))
        pg.click('#m-ok'); pg.wait_for_selector('#prep-apri', timeout=120000); time.sleep(1)
        pg.screenshot(path=str(OUT / 'asm_prepara_fatto.png'))
        print('errori pagina', err)
        b.close()
    for x in sorted(tmp.rglob('DXF laser/*'))[:30]:
        print('  ', x.name)
finally:
    srv.kill()
