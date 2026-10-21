"""Prova dell'interfaccia: raccordo e smusso sugli spigoli di una piastra, rivoluzione da uno sketch (una punta).

    python tools/prova_ui_solidi.py [cartella]        (Python con Playwright; Chromium senza finestra)
"""
import math
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


# il centro di uno spigolo del pezzo sullo schermo (pagina): lo spigolo più in alto a destra, davanti
SPIGOLO = """(k) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get('body'), r = document.querySelector('#c3d').getBoundingClientRect();
  const lst = o.data.edges.map((e, i) => { const a = new T.Vector3(e[0], e[1], e[2]), b = new T.Vector3(e[e.length - 3], e[e.length - 2], e[e.length - 1]);
    return { i, m: a.clone().lerp(b, 0.5), L: a.distanceTo(b) }; }).filter(x => x.L > 20);
  lst.sort((x, y) => (y.m.z - x.m.z) || (x.m.y - y.m.y));
  const q = lst[k].m.clone().project(S.camera);
  return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }"""

srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5145', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5145/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        api('new_project', 'piastra', {'name': 'Piastra', 'larghezza': 150, 'altezza': 100, 'spessore': 12, 'foro': 20})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
        ok('nella scheda PIASTRA ci sono Raccordo e Smusso', pg.is_visible('#ribbon [data-azione="raccordo3d"]') and pg.is_visible('#ribbon [data-azione="smusso3d"]'))
        pg.click('#ribbon [data-azione="raccordo3d"]'); time.sleep(0.3)
        ok('il suggerimento chiede gli spigoli', 'spigoli' in pg.inner_text('#sk-help'))
        for k in (0, 1):
            x, y = pg.evaluate(SPIGOLO, k)
            pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.3)
        ok('due spigoli scelti', '2 scelti' in pg.inner_text('#sk-help'))
        pg.screenshot(path=str(SHOTS / '1_spigoli_scelti.png'))
        pg.keyboard.press('Enter'); pg.wait_for_selector('#dr-v'); pg.fill('#dr-v', '6'); pg.click('#m-ok')
        pg.wait_for_function("JSON.stringify(window.__steelcad.state.tree).includes('Raccordo R6')", timeout=20000); time.sleep(0.8)
        ok('raccordo R6 nell’albero, senza errori', not pg.evaluate('window.__steelcad.state.errors').__len__())
        pg.mouse.move(5, 895); pg.screenshot(path=str(SHOTS / '2_raccordati.png'))
        # rivoluzione: mezza sezione di una punta Ø10 con l'asse di costruzione
        api('new_project', 'zero', {'name': 'Punta'})
        d, L = 10, 133
        cono = (d / 2) / math.tan(math.radians(59))
        api('sketch_add_polyline', 'S1', [[0, 0], [d / 2, 0], [d / 2, L - cono], [0, L]], True)
        api('sketch_add_polyline', 'S1', [[0, -5], [0, L + 5]], False, True)
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("window.__steelcad.enterSketch('S1')"); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(0.8)
        ok('«Rivoluzione» attiva (contorno chiuso + asse)', pg.is_enabled('#ribbon [data-make="revolve"]'))
        pg.click('#ribbon [data-make="revolve"]'); pg.wait_for_selector('#rv-a'); pg.click('#m-ok')
        pg.wait_for_function('!window.__steelcad.sketch && window.__steelcad.objs.has("body")', timeout=20000); time.sleep(1)
        ok('la punta è un solido di rivoluzione', 'Rivoluzione' in str(pg.evaluate('window.__steelcad.state.tree')))
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '3_punta.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
