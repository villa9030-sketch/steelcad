"""Prova dell'interfaccia: lamiera da STEP (la finestra del file la apre Windows: qui si chiama il comando come fa
il pulsante dopo la scelta del file) e lo sviluppo a video.

    python tools/prova_ui_step.py [cartella]
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


# lo STEP di prova: una vaschetta fatta con SteelCAD ed esportata (niente file dei clienti)
SP = str(CART / 'vaschetta.step')
subprocess.run([str(QUI / '.venv/Scripts/python.exe'), '-c', (
    'import sys; sys.path.insert(0, r"' + str(QUI) + '"); from app.service import Service; s = Service(); '
    's.new_project("lamiera", {"name": "Vaschetta", "larghezza": 300, "profondita": 200, "spessore": 2, "raggio": 2, "k": 0.33}); '
    '[s.add_flange("SM1", e, {"length": 40}) for e in ("L1", "L2", "L3", "L4")]; '
    'print(s.export_step(r"' + SP + '")["ok"])')], check=True, creationflags=0x08000000)
srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5147', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5147/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        pg.click('#top .brand'); pg.wait_for_selector('#home:not([hidden])')
        pg.click('#home .home-cat[data-cat="lamiera"]'); time.sleep(0.4)
        ok('nella pagina iniziale c’è «Da uno STEP»', pg.is_visible('#home [data-new="step"]'))
        pg.click('#home [data-new="step"]'); pg.wait_for_selector('#st-k')
        ok('la finestra chiede il K', pg.input_value('#st-k') != '')
        pg.click('#m-no')
        # il file scelto nella finestra di Windows: qui il comando con il percorso
        r = api('import_step', SP, '0,33')
        ok(f'STEP aperto: {str(r.get("message"))[:90]}', r.get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        st = pg.evaluate('window.__steelcad.state')
        ok('è una lamiera con 4 pieghe (tabella pieghe)', len((st.get('sheet') or {}).get('data', {}).get('bend_rows') or []) == 4)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '1_pezzo_da_step.png'))
        pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(1.2); pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '2_sviluppo.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
