r"""Prova delle lavorazioni sui tubi dall'interfaccia, come una persona (22/10): telaio nuovo → clic sulla faccia di
sopra di un traverso → «Disegna sulla faccia di sopra» → cerchio → «Togli materiale» → passante, anche sul tubo
uguale → la cut list ha la riga dei tubi lavorati.

    .venv\Scripts\python.exe tools\prova_ui_tubi.py cartella_screenshot     (usa Edge, già sul PC; niente finestre)
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
SHOTS = Path(sys.argv[1])
PORTA = 5098


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                           env=dict(os.environ, STEELCAD_RULES=str(cart / 'regole.json'), STEELCAD_HOME=str(cart)))
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel='msedge', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)

            def scena_pronta():
                pg.wait_for_function('window.__steelcad.state.scene_version === window.__steelcad.sceneVersion')
                time.sleep(0.4)

            # 1. telaio dalla pagina iniziale
            pg.evaluate("window.__steelcad.nuovo('telaio')")
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.state.cutlist && window.__steelcad.state.cutlist.pieces === 8")
            scena_pronta()
            pg.evaluate("window.__steelcad.runCmd('view_iso')")
            time.sleep(0.8)

            # 2. clic col mouse sulla faccia di sopra del traverso M1
            asta = pg.evaluate("[...window.__steelcad.objs.keys()].find(k => k.endsWith('/M1'))")
            sopra = pg.evaluate("""(id) => { const m = window.__steelcad.objs.get(id).mesh; m.geometry.computeBoundingBox();
                const b = m.geometry.boundingBox; return [(b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, b.max.z]; }""", asta)
            box = pg.locator('#c3d').bounding_box()
            sx, sy = pg.evaluate('(p) => window.__steelcad.toScreen(p)', sopra)
            pg.mouse.move(box['x'] + sx, box['y'] + sy, steps=3)
            pg.mouse.down(); pg.mouse.up()
            pg.wait_for_selector('#p-lav')
            ok(f'clic sul tubo {asta}: pulsante «{pg.inner_text("#p-lav")}»', 'di sopra' in pg.inner_text('#p-lav'))
            pg.screenshot(path=str(SHOTS / 'tubi1_asta.png'))

            # 3. sketch sulla faccia del tubo
            pg.click('#p-lav')
            pg.wait_for_function('window.__steelcad.sketch && window.__steelcad.sketch.v.on_tube')
            time.sleep(0.6)
            dove = pg.inner_text('#sk-where')
            ok(f'sketch sul tubo: «{dove}»', 'sopra' in dove and '0 = la testa' in dove)
            ok('bordi della faccia in arancio', pg.evaluate("window.__steelcad.sketch.v.lines.filter(l => l.ref).length") >= 4)
            pg.screenshot(path=str(SHOTS / 'tubi2_sketch.png'))

            # 4. un cerchio Ø12 a 150 dalla testa, in mezzo alla faccia
            c3d = pg.locator('#c3d').bounding_box()

            def clic(x, y):
                sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [x, y])
                pg.mouse.move(c3d['x'] + sx, c3d['y'] + sy, steps=3)
                pg.mouse.down(); pg.mouse.up()
                time.sleep(0.3)
            pg.keyboard.press('c')
            clic(150, 20)
            clic(156, 20)
            pg.keyboard.press('Escape')
            pg.wait_for_function('window.__steelcad.sketch && window.__steelcad.sketch.v.circles.length === 1')
            ok('cerchio disegnato', True)

            # 5. Togli materiale → finestra della lavorazione: passante, anche sul tubo uguale
            pg.wait_for_selector('#sk-face [data-make="cut"]:not([disabled])')
            pg.click('#sk-face [data-make="cut"]')
            pg.wait_for_selector('#lt-n')
            ok('finestra «Lavorazione sul tubo» con «anche sui tubi uguali»', pg.is_visible('#lt-u'))
            pg.fill('#lt-n', 'Fori Ø12')
            pg.check('input[name="lt-p"][value="1"]')
            pg.screenshot(path=str(SHOTS / 'tubi3_finestra.png'))
            pg.click('#m-ok')
            pg.wait_for_function('!window.__steelcad.sketch')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.some(r => r.lavorata && r.qty === 2)")
            scena_pronta()
            ok('cut list: 2 tubi lavorati su una riga', True)
            albero = pg.inner_text('#tree')
            ok('albero: «Lavorazioni sui tubi / Fori Ø12 su M1, M3 (passante)»',
               'Lavorazioni sui tubi' in albero and 'Fori Ø12 su M1, M3 (passante)' in albero)
            pg.screenshot(path=str(SHOTS / 'tubi4_fatto.png'))

            # 6. riclic sul tubo: la lavorazione è nel pannello, «Modifica» riapre lo sketch
            pg.evaluate("(id) => window.__steelcad.select(id)", asta)
            pg.wait_for_selector('[data-lav-sk]')
            pg.click('[data-lav-sk]')
            pg.wait_for_function('window.__steelcad.sketch && window.__steelcad.sketch.v.circles.length === 1')
            ok('Modifica riapre lo sketch col cerchio', True)
            pg.evaluate('window.__steelcad.exitSketch()')
            time.sleep(0.5)
            ok(f'nessun errore nella pagina {errori[:3]}', not errori)
            b.close()
    finally:
        srv.kill()
    print(f'{sum(esiti)}/{len(esiti)} controlli')
    sys.exit(0 if all(esiti) else 1)


if __name__ == '__main__':
    main()
