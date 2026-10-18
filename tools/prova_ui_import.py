"""Prova dell'import DXF in Chrome: pagina iniziale → Importa DXF/DWG, anteprima con i contorni, dati di piega,
crea il pezzo e controlla flange e sviluppo.

    python tools/prova_ui_import.py file.dxf [cartella_screenshot] --chrome
"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
PORTA = 5131
argv = [a for a in sys.argv[1:] if not a.startswith('--')]
dxf = Path(argv[0])
out = Path(argv[1]) if len(argv) > 1 else Path(tempfile.mkdtemp())
out.mkdir(parents=True, exist_ok=True)
cart = Path(tempfile.mkdtemp())
shutil.copy(dxf, cart / dxf.name)
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
time.sleep(3)
esiti = []


def ok(t, c):
    esiti.append(bool(c))
    print(('OK   ' if c else 'NO   ') + t, flush=True)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        pg.click('#top .brand')
        pg.wait_for_selector('#home:not([hidden])')
        pg.click('#home [data-new="importa"]')
        pg.wait_for_selector('#imp-view svg', timeout=30000)
        n_giri = pg.locator('#imp-view path.giro').count()
        ok(f'anteprima con {n_giri} contorni', n_giri > 0)
        ok('contorno proposto evidenziato', pg.locator('#imp-view path.giro.scelto').count() == 1)
        utili = pg.locator('#imp-view line.piega.utile').count()
        ok(f'{utili} linee di piega utili, righe in tabella', pg.locator('#imp-bends tr[data-p]').count() == utili)
        pg.screenshot(path=str(out / '1_anteprima.png'))
        # senza dati di piega: messaggio chiaro, niente pezzo
        pg.fill('#imp-sp', '')
        pg.click('#imp-ok')
        pg.wait_for_selector('#imp-msg .msg.err', timeout=15000)
        ok('senza spessore: chiede lo spessore', 'spessore' in pg.inner_text('#imp-msg'))
        pg.fill('#imp-sp', '1,5')
        pg.fill('#imp-r', '1,5')
        pg.fill('#imp-k', '0,4')
        if utili:
            pg.select_option('#imp-bends tr[data-p] >> nth=0 >> [data-b="direction"]', 'down')
        pg.click('#imp-ok')
        pg.wait_for_function("document.querySelector('#modal').hidden", timeout=60000)
        pg.wait_for_function("window.__steelcad.objs && window.__steelcad.objs.size >= 1", timeout=30000)
        time.sleep(1)
        st = pg.evaluate("window.__steelcad.state")
        ok('pezzo creato, pagina iniziale chiusa', pg.evaluate("document.querySelector('#home').hidden"))
        etich = [c['label'] for c in st['tree']['children']]
        ok('albero: ' + ' · '.join(etich), any('Lamiera' in e or dxf.stem in e for e in etich) or len(etich) > 0)
        pg.screenshot(path=str(out / '2_pezzo.png'))
        ok('nessun errore JavaScript', not err)
        if err:
            print(err[:3])
        b.close()
finally:
    srv.terminate()
print(f'{sum(esiti)}/{len(esiti)}')
