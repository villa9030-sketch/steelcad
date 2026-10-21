"""Prova dell'interfaccia: lo strumento Quota nello sketch, cliccando come l'utente.

    python tools/prova_ui_quote.py [cartella]

Rettangolo 100 × 60: Quota → clic sul lato di sotto → scrivo 150 → Invio (il lato diventa 150); clic sulla quota
che c'è → la cambio; cerchio → diametro; due punti → distanza orizzontale.
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


srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5148', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
SCHERMO = """(xy) => { const [x, y] = window.__steelcad.skScreen(xy), r = document.querySelector('#c3d').getBoundingClientRect(); return [r.left + x, r.top + y]; }"""
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5148/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        api('new_project', 'zero', {'name': 'Quote'})
        sid = 'S1'
        api('sketch_add_rectangle', sid, [0, 0], [100, 60])
        api('sketch_add_circle', sid, [50, 30], 10)
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", sid); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1.5)

        def clic(xy):
            x, y = pg.evaluate(SCHERMO, xy)
            pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.6)

        def lato_sotto():
            v = pg.evaluate('window.__steelcad.sketch.v')
            l = min(v['lines'], key=lambda l: (l['pa'][1] + l['pb'][1]))
            import math
            return math.dist(l['pa'], l['pb'])

        pg.click('#ribbon [data-tool="dim"]'); time.sleep(0.3)
        ok('Quota: il suggerimento spiega cosa cliccare', 'Quota' in pg.inner_text('#sk-help') or 'linea' in pg.inner_text('#sk-help'))
        clic([50, 0])                                       # il lato di sotto
        pg.screenshot(path=str(SHOTS / '1_dopo_clic_lato.png'))
        campo = pg.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.className, a.value] : null; }")
        ok(f'dopo il clic sul lato si scrive subito la misura (campo attivo: {campo})', campo and campo[0] == 'INPUT')
        pg.keyboard.press('Control+A'); pg.keyboard.type('150'); pg.keyboard.press('Enter'); time.sleep(1.2)
        ok(f'il lato di sotto è diventato 150 (è {lato_sotto():.2f})', abs(lato_sotto() - 150) < 0.01)
        pg.screenshot(path=str(SHOTS / '2_lato_150.png'))
        # cerchio → diametro
        clic([60, 30])
        campo = pg.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.value] : null; }")
        ok(f'clic sul cerchio: scrivo il diametro (campo {campo})', campo and campo[0] == 'INPUT')
        pg.keyboard.press('Control+A'); pg.keyboard.type('30'); pg.keyboard.press('Enter'); time.sleep(1.2)
        r = pg.evaluate("window.__steelcad.sketch.v.circles[0].r")
        ok(f'diametro 30 (raggio {r:.2f})', abs(r - 15) < 0.01)
        pg.screenshot(path=str(SHOTS / '3_diametro.png'))
        # clic su una quota che c'è (l'altezza 60) e la cambio a 80
        pg.keyboard.press('Escape'); time.sleep(0.3)
        ok('Esc spegne lo strumento Quota ma resta nello sketch', pg.evaluate('!!window.__steelcad.sketch'))
        el = pg.locator('#dims .dim', has_text='60').first
        el.click(); time.sleep(0.4)
        campo = pg.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.value] : null; }")
        ok(f'clic sulla quota 60: si può scrivere (campo {campo})', campo and campo[0] == 'INPUT')
        pg.keyboard.press('Control+A'); pg.keyboard.type('80'); pg.keyboard.press('Enter'); time.sleep(1.2)
        v = pg.evaluate('window.__steelcad.sketch.v')
        alto = max(q['xy'][1] for q in v['points']) - min(q['xy'][1] for q in v['points'])
        ok(f'altezza diventata 80 (è {alto:.2f})', abs(alto - 80) < 0.01)
        pg.screenshot(path=str(SHOTS / '4_quota_80.png'))
        # fuori dallo sketch: le quote del pezzo sul 3D (una piastra 300 x 200)
        pg.keyboard.press('Escape'); time.sleep(0.3)
        ok('il secondo Esc esce dallo sketch', pg.evaluate('!window.__steelcad.sketch'))
        api('new_project', 'piastra', {'name': 'P', 'larghezza': 300, 'altezza': 200, 'spessore': 10, 'foro': 20})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        etichette = pg.evaluate("[...document.querySelectorAll('#dims .dim')].map(e => e.textContent)")
        ok(f'sul pezzo si vedono le quote: {etichette}', len(etichette) >= 2)
        el = pg.locator('#dims .dim', has_text='300').first
        el.click(); time.sleep(0.4)
        pg.keyboard.press('Control+A'); pg.keyboard.type('350'); pg.keyboard.press('Enter'); time.sleep(1.5)
        lungo = pg.evaluate("window.__steelcad.state.parameters.find(p => /larg/i.test(p.name)).resolved")
        ok(f'clic sulla quota 300 del pezzo → 350 (larghezza {lungo})', abs(lungo - 350) < 0.01)
        pg.screenshot(path=str(SHOTS / '5_pezzo_350.png'))
        # foro su una faccia della lamiera, quotato dal bordo: clic sul centro, clic sul bordo arancio, scrivo 30
        api('new_project', 'lamiera', {'name': 'L', 'larghezza': 200, 'profondita': 100, 'spessore': 2})
        sid2 = api('sketch_on_face', 'SM1/sopra')['sketch']
        api('sketch_add_circle', sid2, [60, 50], 5)
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", sid2); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1.5)
        v = pg.evaluate('window.__steelcad.sketch.v')
        c = v['circles'][-1]['xc']
        sx = min(q['xy'][0] for q in v['points'] if q['id'] != 'O')
        pg.click('#ribbon [data-tool="dim"]'); time.sleep(0.3)
        clic(c)                                             # il centro del foro
        aiuto = pg.inner_text('#sk-help')
        ok(f'clic sul centro del foro: chiede l’altro punto o la linea ({aiuto[:50]})', 'altro punto' in aiuto or 'linea' in aiuto)
        clic([sx, c[1] + 20])                               # il bordo sinistro (arancio)
        campo = pg.evaluate("() => { const a = document.activeElement; return a ? [a.tagName, a.value] : null; }")
        ok(f'clic sul bordo: scrivo la distanza (campo {campo})', campo and campo[0] == 'INPUT')
        pg.keyboard.press('Control+A'); pg.keyboard.type('30'); pg.keyboard.press('Enter'); time.sleep(1.2)
        v = pg.evaluate('window.__steelcad.sketch.v')
        dx = v['circles'][-1]['xc'][0] - sx
        ok(f'il foro è a 30 dal bordo (è a {dx:.2f})', abs(dx - 30) < 0.01)
        pg.screenshot(path=str(SHOTS / '6_foro_dal_bordo.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
