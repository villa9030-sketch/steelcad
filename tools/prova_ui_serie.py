r"""Prova della «Serie» con anteprima e della finestra del testo che non copre il punto (03/11): porta ugelli
300 × 120 sp. 2, un foro Ø10,2 a 50;90, Serie 6 × 40 (le copie si vedono prima di confermare), poi un testo sotto
l'ultimo foro a destra: la finestra di lato non deve coprirlo.

    <python con playwright> tools\prova_ui_serie.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando, comando_visibile  # noqa: F401  (comandi della barra, anche in «Altro ▾»)

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
            api('new_project', 'lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.33})
            sid = api('sketch_on_face', 'SM1/sopra')['sketch']
            api('sketch_add_circle', sid, [50, 90], 5.1)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            time.sleep(1.5)
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            comando(pg, '#ribbon [data-tool="select"]')
            pg.mouse.click(*a_schermo([55.1, 90]))
            time.sleep(0.4)
            comando(pg, '#ribbon [data-act="pattern"]')
            pg.wait_for_selector('#p-c', timeout=10000)
            pg.locator('#p-c').fill('6')
            pg.locator('#p-c').dispatch_event('input')
            pg.locator('#p-px').fill('40')
            pg.locator('#p-px').dispatch_event('input')
            pg.locator('#p-r').fill('1')
            pg.locator('#p-r').dispatch_event('input')
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '01_serie_anteprima.png'))
            ok('frase della serie', '6 in tutto' in pg.locator('#p-frase').inner_text())
            n_prova = pg.evaluate('window.__steelcad.sketch.serieProva ? window.__steelcad.sketch.serieProva.c : 0')
            ok('copie in prova sul disegno', n_prova == 6)
            pg.locator('#m-ok').click()
            time.sleep(2.0)
            ok('6 cerchi', len([c for c in pg.evaluate('window.__steelcad.sketch.v.circles') if not c['ref']]) == 6)
            # 03/11 secondo giro: il passo della serie a sinistra col suo nome da officina, non «px1»
            par = pg.locator('#params').inner_text()
            print('misure:', par.replace(chr(10), ' / '))
            ok('passo della serie: «Distanza tra i fori della fila» in grassetto', pg.locator('#params b', has_text='Distanza tra i fori della fila').count() == 1)
            pg.screenshot(path=str(SHOTS / '01b_passo_con_nome.png'))
            # il testo sotto l'ultimo foro a destra
            comando(pg, '#ribbon [data-tool="text"]')
            xt, yt = a_schermo([250, 78])
            pg.mouse.move(xt, yt)
            pg.mouse.click(xt, yt)
            pg.wait_for_selector('#tx-t', timeout=10000)
            time.sleep(0.8)
            pg.locator('#tx-t').fill('3.0')
            pg.locator('#tx-t').dispatch_event('input')
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '02_testo_non_coperto.png'))
            xt2, _ = a_schermo([250, 78])
            sx = pg.locator('#modal-box').bounding_box()['x']
            ok('il punto del testo resta a sinistra della finestra', xt2 < sx - 20)
            pg.keyboard.press('Escape')
            time.sleep(0.5)
            # una scritta sotto ogni foro, in una volta
            comando(pg, '#ribbon [data-tool="select"]')
            pg.keyboard.press('Control+A')
            time.sleep(0.3)
            comando(pg, '#ribbon [data-act="scritte"]')
            pg.wait_for_selector('[data-ss="5"]', timeout=10000)
            for i, t in enumerate(['1.0', '1.2', '1.5', '2.0', '2.5', '3.0']):
                pg.locator(f'[data-ss="{i}"]').fill(t)
            pg.locator('[data-ss="5"]').dispatch_event('input')
            pg.wait_for_function("document.getElementById('ss-frase')?.textContent.startsWith('6 scritte')", timeout=60000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '03_scritte_sotto_i_fori.png'))
            pg.locator('#m-ok').click()
            time.sleep(2.0)
            testi = pg.evaluate('window.__steelcad.sketch.v.texts')
            ok('6 scritte sotto i fori', sorted(t['text'] for t in testi) == ['1.0', '1.2', '1.5', '2.0', '2.5', '3.0'])
            pg.screenshot(path=str(SHOTS / '04_scritte_messe.png'))
            # raggio e K accanto alle misure, a sinistra
            pg.locator('#sk-done').first.click()
            time.sleep(1.5)
            ok('R e K a sinistra con le misure', pg.locator('[data-tech-sx="radius"]').count() == 1 and pg.locator('[data-tech-sx="k"]').count() == 1)
            pg.screenshot(path=str(SHOTS / '05_misure_con_R_e_K.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
