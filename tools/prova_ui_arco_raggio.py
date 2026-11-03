r"""Prova dell'«Arco col raggio» (03/11), come una persona: «Da zero», linea 28, «Arco col raggio» mezzo giro a
squadra, scrivo 55, poi la linea riparte dalla fine dell'arco: 28. Il collare deve venire 166 di fuori tutto.

    <python con playwright> tools\prova_ui_arco_raggio.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5262
CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    env = dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart))
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1500, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            api = lambda nome, *a: pg.evaluate("([n, a]) => fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())", [nome, list(a)])  # noqa: E731
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            api('new_project', 'zero', {'name': 'Collare'})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(0.8)
            sid = 'S1'                                           # lo sketch del progetto «Da zero»
            if not pg.evaluate('!!window.__steelcad.sketch'):
                pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            time.sleep(1.0)
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            # la prima gamba: clic sullo zero, mouse a destra, 28 Invio, Esc
            pg.locator('#ribbon [data-tool="line"]').first.click()
            x0, y0 = a_schermo([0, 0])
            pg.mouse.move(x0, y0)
            pg.mouse.click(x0, y0)
            pg.mouse.move(x0 + 200, y0)
            pg.keyboard.type('28')
            pg.keyboard.press('Enter')
            time.sleep(0.3)
            pg.keyboard.press('Escape')
            time.sleep(1.2)
            # l'arco: parte da solo dalla fine della linea
            pg.locator('#ribbon [data-tool="arcr"]').first.click()
            time.sleep(0.4)
            pg.locator('[data-arcr-g="180"]').click()
            pg.locator('[data-arcr-p="squadra"]').click()
            xa, ya = a_schermo([27, 4])
            pg.mouse.move(xa, ya)
            pg.keyboard.type('55')
            time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '01_arco_anteprima.png'))
            pg.keyboard.press('Enter')
            time.sleep(1.5)
            # la seconda gamba dalla fine dell'arco (la linea è già accesa da lì)
            xe, ye = a_schermo([160, 0])
            pg.mouse.move(xe, ye)
            time.sleep(0.2)
            pg.keyboard.type('28')
            pg.screenshot(path=str(SHOTS / '02_seconda_gamba.png'))
            pg.keyboard.press('Enter')
            time.sleep(0.3)
            pg.keyboard.press('Escape')
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '03_profilo_finito.png'))
            v = pg.evaluate('window.__steelcad.sketch.v')
            linee = [(l['xa'], l['xb']) for l in v['lines'] if not l['ref']]
            archi = [(a['xc'], a['r'], a['a1'] - a['a0']) for a in v['arcs']]
            print('linee', linee, 'archi', archi)
            ok('due gambe da 28', len(linee) == 2 and all(abs(((q[0] - p_[0]) ** 2 + (q[1] - p_[1]) ** 2) ** 0.5 - 28) < 1e-6 for p_, q in linee))
            ok('arco R55 mezzo giro', len(archi) == 1 and abs(archi[0][1] - 55) < 1e-9 and abs(archi[0][2] - 3.141592653589793) < 1e-9)
            r = api('create_from_sketch', sid, 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, 'raggio': 1, 'k': 0.4})
            print(r.get('message'))
            pg.evaluate('(r) => window.__steelcad.apply(r)', r)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '04_collare.png'))
            ok('collare fatto', r.get('ok'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
