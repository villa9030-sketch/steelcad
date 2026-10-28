"""Prova dell'interfaccia: le viste delle tavole (28/10) — l'alto resta sotto la fronte quando lo sposti, la fronte si
porta dietro le altre, fianco da destra, isometrica tolta, una vista tolta, il dettaglio ingrandito.

    python tools/prova_ui_tavole_viste.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5206', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5206/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('esempio', 'staffa')
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.4)
        pg.evaluate("window.__steelcad.runCmd('drawings')")
        pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(0.8)
        T = lambda v: pg.evaluate("v => window.__tavole.foglio().oggetti.find(o => o.id === v)?.T", v)

        def trascina(v, dx, dy):
            bb = pg.locator(f'#te-foglio [data-el="{v}"]').first.bounding_box()
            x, y = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
            pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + dx, y + dy, steps=6); pg.mouse.up(); time.sleep(1.8)
        f0, a0, s0 = T('vista:fronte'), T('vista:alto'), T('vista:sinistra')
        trascina('vista:alto', 60, 25)
        a1 = T('vista:alto')
        chk(f'l’alto spostato di lato resta sotto la fronte (x {a0[1]:.1f} → {a1[1]:.1f}, y {a0[2]:.1f} → {a1[2]:.1f})',
            abs(a1[1] - a0[1]) < 0.01 and abs(a1[2] - a0[2]) > 1)
        trascina('vista:fronte', 30, 0)
        f1, a2, s1 = T('vista:fronte'), T('vista:alto'), T('vista:sinistra')
        chk('la fronte si porta dietro l’alto e il fianco', abs((f1[1] - f0[1]) - (a2[1] - a1[1])) < 0.01 and abs((f1[1] - f0[1]) - (s1[1] - s0[1])) < 0.01 and abs(f1[1] - f0[1]) > 1)
        pg.screenshot(path=str(OUT / '1_allineate.png'))
        # «allineata» tolta: l'alto si sposta libero
        pg.locator('#te-foglio [data-el="vista:alto"]').first.click(force=True); time.sleep(0.5)
        chk('nel pannello dell’alto: «allineata alla vista di fronte»', pg.is_visible('#ts-allinea') and pg.is_checked('#ts-allinea'))
        pg.click('#ts-allinea'); time.sleep(1.5)
        a3 = T('vista:alto')
        trascina('vista:alto', 50, 0)
        chk('non allineata: si sposta anche di lato', abs(T('vista:alto')[1] - a3[1]) > 1)
        # fianco da destra, isometrica no
        pg.select_option('[data-c="fianco"]', 'destra'); time.sleep(2.5)
        ids = pg.evaluate("window.__tavole.foglio().oggetti.map(o => o.id)")
        chk('vista da destra: ' + str([i for i in ids if i.startswith('vista:')]), 'vista:destra' in ids and 'vista:sinistra' not in ids)
        chk('la vista da destra sta a sinistra della fronte (proiezione europea)', T('vista:destra')[1] < T('vista:fronte')[1])
        pg.select_option('[data-c="isometrica"]', 'no'); time.sleep(2.5)
        chk('isometrica tolta', 'vista:iso' not in pg.evaluate("window.__tavole.foglio().oggetti.map(o => o.id)"))
        pg.screenshot(path=str(OUT / '2_destra_senza_iso.png'))
        # togli una vista
        pg.locator('#te-foglio [data-el="vista:destra"]').first.click(force=True); time.sleep(0.5)
        pg.click('#ts-togli'); time.sleep(1.8)
        chk('vista da destra tolta', 'vista:destra' not in pg.evaluate("window.__tavole.foglio().oggetti.map(o => o.id)"))
        chk('nell’elenco: «tolta»', 'tolta' in pg.inner_text('#te-rit'))
        # dettaglio: centro e raggio sulla fronte
        pg.click('[data-str="dettaglio"]'); time.sleep(0.3)
        # il punto del foglio (mm, y in su) a 3/4 della vista di fronte, portato sullo schermo
        cx, cy = pg.evaluate("""() => { const o = window.__tavole.foglio().oggetti.find(o => o.id === 'vista:fronte'), [x0, y0, x1, y1] = o.bbox;
          const svg = document.querySelector('#te-foglio svg'), H = window.__tavole.foglio().size[1], q = svg.createSVGPoint();
          q.x = x0 + (x1 - x0) * 0.97; q.y = H - (y0 + (y1 - y0) * 0.1); const r = q.matrixTransform(svg.getScreenCTM()); return [r.x, r.y]; }""")
        pg.mouse.click(cx, cy); time.sleep(0.3)
        pg.mouse.click(cx + 25, cy); time.sleep(2.5)
        ids = pg.evaluate("window.__tavole.foglio().oggetti.map(o => o.id)")
        chk('dettaglio A sul foglio', 'dettaglio:A' in ids)
        svg = pg.inner_html('#te-foglio')
        chk('titolo «DETTAGLIO A (…)»', 'DETTAGLIO A (' in svg)
        chk('pannello del dettaglio con l’ingrandimento', pg.is_visible('#ts-k'))
        pg.select_option('#ts-k', '4'); time.sleep(2)
        r = api('drawing_preview', None)['sheets'][0]['ritocchi']
        chk('ingrandimento × 4 salvato', (r.get('dettagli') or [{}])[0].get('k') == 4)
        pg.screenshot(path=str(OUT / '3_dettaglio.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
