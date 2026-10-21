"""Prova dell'interfaccia: testo da marcare col laser su una faccia della lamiera, cliccando come l'utente.

    python tools/prova_ui_testi.py [cartella]        (Python con Playwright; Chromium senza finestra)
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


srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5144', '--cartella', str(CART)],
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
        pg.goto('http://127.0.0.1:5144/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        api('new_project', 'lamiera', {'name': 'Targhetta', 'larghezza': 200, 'profondita': 100, 'spessore': 2})
        api('add_flange', 'SM1', 'L1', {'length': 40})
        sid = api('sketch_on_face', 'SM1/sopra')['sketch']
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", sid); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(0.8)
        ok('nello sketch c’è il pulsante «Testo»', pg.is_visible('#ribbon [data-tool="text"]'))
        pg.click('#ribbon [data-tool="text"]'); time.sleep(0.3)
        ok('il suggerimento in basso spiega il Testo', 'Testo' in pg.inner_text('#sk-help'))
        time.sleep(1.5)                                   # l'inquadratura dello sketch si assesta
        x, y = pg.evaluate("() => { const [x, y] = window.__steelcad.skScreen([30, 40]), r = document.querySelector('#c3d').getBoundingClientRect(); return [r.left + x, r.top + y]; }")
        pg.mouse.move(x, y); time.sleep(0.3)
        pg.mouse.click(x, y)
        pg.wait_for_selector('#tx-t', timeout=8000)
        pg.fill('#tx-t', 'PP-001 Ø10'); pg.fill('#tx-h', '10'); pg.click('#m-ok')
        pg.wait_for_function("(window.__steelcad.sketch.v.texts || []).length === 1", timeout=10000); time.sleep(0.6)
        v = pg.evaluate('window.__steelcad.sketch.v')
        ok(f'il testo c’è nello sketch, disegnato a tratti ({len(v["texts"][0]["strokes"])} tratti)', len(v['texts'][0]['strokes']) > 5)
        ok(f'il testo comincia dove ho cliccato ({v["texts"][0]["xy"]})', abs(v['texts'][0]['xy'][0] - 30) < 2 and abs(v['texts'][0]['xy'][1] - 40) < 2)
        ok('«Marca col laser» è attivo', pg.is_enabled('#sk-mark'))
        pg.screenshot(path=str(SHOTS / '1_testo_nello_sketch.png'))
        pg.click('#sk-mark')
        pg.wait_for_function('!window.__steelcad.sketch', timeout=20000); time.sleep(1)
        st = pg.evaluate('window.__steelcad.state')
        ok('nell’albero c’è la Marcatura', 'Marcatura' in str(st['tree']))
        sc = api('scene')
        ok(f'i segni si vedono sul pezzo ({len(sc.get("marks") or [])} tratti)', len(sc.get('marks') or []) > 5)
        # il DXF col layer MARK lo prova tests/test_marcatura.py (qui l'esporta chiede il file con la finestra)
        pg.evaluate("window.__steelcad.runCmd('view_top')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '2_marcatura_sul_pezzo.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
