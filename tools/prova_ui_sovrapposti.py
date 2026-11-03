r"""Prova di «Due contorni si sovrappongono» che dice dove (03/11): porta ugelli con la scritta «1.2» messa due volte
nello stesso punto, «Togli materiale»: i contorni in rosso e «Tienine una»; dopo, il taglio si può fare.

    <python con playwright> tools\prova_ui_sovrapposti.py cartella_screenshot [porta]
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
            api('new_project', 'lamiera', {'larghezza': 300, 'profondita': 120, 'spessore': 2, 'raggio': 1, 'k': 0.33})
            sid = api('sketch_on_face', 'SM1/sopra')['sketch']
            api('sketch_add_circle', sid, [50, 90], 5.1)
            for _ in range(2):
                api('sketch_add_text', sid, [50, 78], '1.2', 5, 0, 'saira', True)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            time.sleep(1.5)
            pg.locator('#ribbon [data-make="cut"]').first.click()
            pg.wait_for_selector('#sovr-card', timeout=60000)
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '01_sovrapposti_in_rosso.png'))
            ok('la scheda dice cosa', 'la scritta «1.2»' in pg.locator('#sovr-card').inner_text())
            ok('la scheda dice che rifà il taglio da solo', 'rifà subito il taglio' in pg.locator('#sovr-card').inner_text())
            # i messaggi in basso, tutti (spariscono da soli dopo qualche secondo)
            pg.evaluate("window.__msg = []; new MutationObserver(m => m.forEach(x => x.addedNodes.forEach(n => n.classList?.contains('toast') && window.__msg.push(n.textContent)))).observe(document.body, {childList: true, subtree: true})")
            pg.locator('#sovr-card [data-tieni]').click()
            pg.wait_for_function("document.querySelector('#prova-barra') && !document.querySelector('#prova-barra.no') && !document.querySelector('#prova-barra.calcolo') || !window.__steelcad.sketch", timeout=60000)
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '02_dopo_tienine_una.png'))
            # tolta la copia, il taglio riparte da solo (era quello che avevi chiesto) e va
            ok('dopo «Tienine una» il taglio è fatto', not pg.evaluate('!!window.__steelcad.sketch') and 'Foro Ø10,2' in pg.locator('#tree').inner_text())
            toast = ' | '.join(pg.evaluate('window.__msg'))
            print('messaggi:', toast)
            ok('il messaggio dice copia tolta e taglio fatto', 'Tolta 1 copia doppia e fatto il taglio' in toast)
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
