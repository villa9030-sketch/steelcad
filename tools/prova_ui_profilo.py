"""Prova dell'interfaccia: profilo disegnato (U col fondo tondo) estruso in lamiera, l'arco a colpi (bumping).

    python tools/prova_ui_profilo.py [cartella]        (Python con Playwright; Chromium senza finestra)
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
(CART / 'r.json').write_text('{"format": "steelcad-regole", "rules": [], "default": {"radius": 1, "method": "k", "k": 0.21}}', encoding='utf-8')
risultati = []


def ok(cosa, esito):
    risultati.append(esito)
    print(('OK   ' if esito else 'NO   ') + cosa, flush=True)


srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5142', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_RULES=str(CART / 'r.json'), STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5142/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        call = lambda n, *a: pg.evaluate("async ([n, a]) => { const r = await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json(); if (r.state && window.__steelcad.sketch) await window.__steelcad.apply(r); return r; }", [n, list(a)])  # noqa: E731
        call('new_project', 'zero', {'name': 'Canala coclea'})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        sid = 'S1'                                         # lo sketch del pezzo nuovo «da disegnare»
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", sid); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(0.6)
        call('sketch_add_polyline', sid, [[-115, 150], [-115, 0]], False)
        call('sketch_add_arc3', sid, [-115, 0], [0, -115], [115, 0])
        call('sketch_add_polyline', sid, [[115, 0], [115, 150]], False)
        time.sleep(0.6)
        ok('nello sketch c’è «Estrudi in lamiera» ed è attivo con la U aperta', pg.is_enabled('#ribbon [data-make="profilo"]'))
        pg.screenshot(path=str(SHOTS / '1_profilo.png'))
        pg.click('#ribbon [data-make="profilo"]'); pg.wait_for_selector('#pf-L')
        pg.fill('#pf-L', '1000'); pg.fill('#pf-sp', '3'); pg.fill('#pf-colpi', '14')
        pg.screenshot(path=str(SHOTS / '2_finestra.png'))
        pg.click('#m-ok')
        pg.wait_for_function('!window.__steelcad.sketch && window.__steelcad.state.sheet', timeout=30000); time.sleep(1)
        st = pg.evaluate('window.__steelcad.state')
        righe = st['sheet']['data']['bend_rows']
        ok(f'lamiera fatta: {len(righe)} pieghe da {righe[0]["angle"]:.2f}° (14 colpi per 180°)', len(righe) == 14 and abs(righe[0]['angle'] - 180 / 14) < 1e-6)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '3_canala.png'))
        pg.evaluate("window.__steelcad.runCmd('view_front')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '4_di_fronte.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
