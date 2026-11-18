"""Prova dell'interfaccia del taglio «attraverso tutto il pezzo» (18/11, carrello): fori Ø9 sulla piega davanti di una
vaschetta 800×600 (pieghe 50, ritorni 20). «Togli materiale» chiede: Solo questa parete / Attraverso tutto il pezzo
(nomina la piega dietro); scelto «tutto» → 4 fori nello sviluppo. Fori in mezzo alla base: nessuna domanda.

    python tools/prova_ui_taglio_passante.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5331
OUT.mkdir(parents=True, exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'):
    pass
ok = []


def chk(c, e):
    ok.append(bool(e))
    print(('OK  ' if e else 'NO  ') + c, flush=True)


CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        api('new_project', 'lamiera', {'name': 'Ripiano', 'larghezza': 800, 'profondita': 600, 'spessore': 3, 'raggio': 1, 'k': 0.21})
        for lato in ('L1', 'L2', 'L3', 'L4'):
            api('add_flange', 'SM1', lato, {'length': 50})
        fl = {}
        for x in api('state')['tree']['children'][0]['children']:
            if x['kind'] == 'flange':
                fl[x['label']] = x['ref'].split('/')[1]
        for nome, fid in list(fl.items()):
            api('add_flange', 'SM1', None, {'length': 20}, fid)
        davanti = next(f for n, f in fl.items() if 'davanti' in n)
        sid = api('sketch_on_face', f'SM1/{davanti}/esterno')['sketch']
        for q in ((20, 25), (780, 25)):
            api('sketch_add_circle', sid, list(q), 4.5)
        pg.reload()
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
        time.sleep(1.5)
        pg.evaluate('window.__steelcad.hideHome()')
        pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
        pg.wait_for_function('window.__steelcad.sketch')
        time.sleep(1.2)
        pg.click('#sk-face [data-make="cut"]')
        pg.wait_for_selector('#m-tutto', timeout=20000)
        testo = pg.inner_text('#modal')
        chk(f'chiede solo questa parete / tutto il pezzo ({testo[:90]!r})', 'Solo questa parete' in testo and 'Piega dietro' in testo)
        time.sleep(0.8)
        pg.screenshot(path=str(OUT / 'tp1_domanda.png'))
        pg.click('#m-tutto')
        for _ in range(60):
            st = api('state')
            if 'Taglio passante' in str(st['tree']):
                break
            time.sleep(0.5)
        chk('nell’albero «Taglio passante»', 'Taglio passante' in str(st['tree']))
        time.sleep(1.5)
        pg.screenshot(path=str(OUT / 'tp2_fatto.png'))
        # in mezzo alla base: niente da chiedere, taglia subito come prima
        sid2 = api('sketch_on_face', 'SM1/sopra')['sketch']
        api('sketch_add_circle', sid2, [400, 300], 20)
        pg.reload()
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
        time.sleep(1.5)
        pg.evaluate('window.__steelcad.hideHome()')
        pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid2)
        pg.wait_for_function('window.__steelcad.sketch')
        time.sleep(1.2)
        pg.click('#sk-face [data-make="cut"]')
        for _ in range(60):
            st = api('state')
            if str(st['tree']).count("'sheet_cut'") == 2:
                break
            time.sleep(0.5)
        chk('foro in mezzo alla base: nessuna domanda, tagliato', str(st['tree']).count("'sheet_cut'") == 2
            and pg.locator('#m-tutto').count() == 0)
        # l'angolo del ripiano del carrello: finestra 41×41 sulla base, passante → via anche raggi e ritorni
        copia = cart / 'RIPIANO.steelcad'
        copia.write_bytes((ROOT / 'tests' / 'data' / 'carrello' / 'ripiano_angolo.steelcad').read_bytes())
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/open_path', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }", [str(copia)])
        time.sleep(1.5)
        pg.evaluate("(s) => window.__steelcad.enterSketch(s)", 'S4')
        pg.wait_for_function('window.__steelcad.sketch')
        time.sleep(1.2)
        pg.click('#sk-face [data-make="cut"]')
        pg.wait_for_selector('#m-tutto', timeout=30000)
        time.sleep(0.8)
        testo = pg.inner_text('#modal')
        chk(f'angolo: dice pieghe tolte e striscia di 0,25 ({testo[:160]!r})', 'pieghe' in testo and '0,25' in testo)
        pg.screenshot(path=str(OUT / 'tp3_angolo_domanda.png'))
        pg.click('#m-tutto')
        for _ in range(60):
            st = api('state')
            if 'Taglio passante' in str(st['tree']):
                break
            time.sleep(0.5)
        chk('angolo: «Taglio passante» fatto', 'Taglio passante' in str(st['tree']))
        time.sleep(1.5)
        pg.screenshot(path=str(OUT / 'tp4_angolo_fatto.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
