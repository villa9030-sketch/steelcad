"""Prova dell'interfaccia: una vite della libreria nel foro di una piastra, cliccando come l'utente.

    python tools/prova_ui_viteria.py [cartella]        (Python con Playwright; Chromium senza finestra)
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

QUI = Path(__file__).resolve().parents[1]
CART = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
SHOTS = CART / 'shots'; SHOTS.mkdir(parents=True, exist_ok=True)
risultati = []


def ok(cosa, esito):
    risultati.append(esito)
    print(('OK   ' if esito else 'NO   ') + cosa, flush=True)


srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5146', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(CART), USERPROFILE=str(CART), HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5146/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        api('new_project', 'piastra', {'name': 'Piastra', 'larghezza': 120, 'altezza': 80, 'spessore': 10, 'foro': 6.4})
        api('save', str(CART / 'Piastra.steelcad'))
        api('new_assembly', 'Viteria'); api('asm_insert', str(CART / 'Piastra.steelcad'))
        api('save', str(CART / 'viteria.steelcad-asm'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
        ok('nella barra dell’assieme c’è «Viteria»', pg.is_visible('#ribbon [data-cmd="asm_viteria"]'))
        # clic sulla parete del foro
        foro = pg.evaluate("""() => { const S = window.__steelcad, o = S.objs.get('I1'); return o.data.faces.find(f => /foro|cerchio|C\d/i.test(f.label || f.name || ''))?.index ?? null; }""")
        r = api('asm_state') if False else None
        idx = None
        for f in pg.evaluate("() => window.__steelcad.objs.get('I1').data.faces.map(f => f.index)"):
            if api('select', 'I1', f).get('selection', {}).get('face', {}).get('kind') == 'cilindrica':
                idx = f
                break
        pg.evaluate("([id, f]) => window.__steelcad.select(id, f)", ['I1', idx]); time.sleep(0.8)
        pg.click('#ribbon [data-cmd="asm_viteria"]'); pg.wait_for_selector('#vt-t')
        ok('la finestra propone «nel foro che hai cliccato»', pg.is_visible('#vt-f') and pg.is_checked('#vt-f'))
        pg.select_option('#vt-t', 'vite_tcei'); pg.select_option('#vt-m', 'M6'); pg.select_option('#vt-l', '20')
        pg.click('#m-ok')
        pg.wait_for_function("JSON.stringify(window.__steelcad.state.tree).includes('TCEI M6x20')", timeout=30000); time.sleep(1)
        st = pg.evaluate('window.__steelcad.state')
        ok('vite TCEI M6x20 nell’assieme, accoppiata al foro', 'foro su foro' in str(st['tree']) and not st['warnings'])
        ok('in distinta tra gli acquisti', any(x.get('acquisto') for x in st['bom']))
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '1_vite_nel_foro.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
