"""Prova dell'interfaccia: la vista resta ferma mentre si disegna (03/11, percorso D: dopo il primo foro la vista si
abbassava di 22 px e chi cliccava dove aveva visto metteva i fori a 280/180 invece di 275/175).

    python tools/prova_ui_vista_ferma.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5272
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
while not srv.stdout.readline().startswith(b'http'):
    pass
esiti = []


def ok(t, c):
    esiti.append(bool(c))
    print(('OK   ' if c else 'NO   ') + t, flush=True)


CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        pg.click('.home-nuovo[data-new="lamiera"]'); time.sleep(3)
        for k, v in (('W', '300'), ('P', '200'), ('sp', '8')):
            pg.click(f'input[data-p="{k}"]', click_count=3); pg.keyboard.type(v); pg.keyboard.press('Enter'); time.sleep(1.2)
        pg.mouse.move(760, 480); time.sleep(0.3); pg.mouse.click(760, 480); time.sleep(1.2)
        pg.click('#mini-barra button:has-text("Disegna qui")'); time.sleep(3)
        pg.click('[data-tool="circle"]'); time.sleep(0.5)

        def schermo(P):
            x, y = pg.evaluate('p => window.__steelcad.skScreen(p)', P)
            r = pg.evaluate("document.querySelector('#c3d').getBoundingClientRect().toJSON()")
            return x + r['left'], y + r['top']
        alta = lambda: pg.evaluate("document.querySelector('#view').clientHeight")  # noqa: E731
        h0 = alta()
        punti = [schermo(P) for P in ([25, 25], [275, 25], [275, 175], [25, 175])]   # dove li vede adesso
        for x, y in punti:
            pg.mouse.move(x, y); time.sleep(0.3); pg.mouse.click(x, y); time.sleep(0.3); pg.mouse.move(x + 15, y); time.sleep(0.2)
            pg.keyboard.type('13'); pg.keyboard.press('Enter'); time.sleep(1.0)
            ok(f'dopo il foro la vista è alta uguale ({alta()} px)', alta() == h0)
        cerchi = [tuple(c['xc']) for c in pg.evaluate('window.__steelcad.sketch.v')['circles']]
        ok(f'i 4 fori dove li ha visti: {cerchi}', cerchi == [(25, 25), (275, 25), (275, 175), (25, 175)])
        pg.mouse.move(900, 600); time.sleep(0.4)
        pg.screenshot(path=str(out / 'v1_quattro_fori.png'))
        pg.keyboard.press('Escape'); time.sleep(0.3); pg.click('#ribbon [data-skdone]') if pg.is_visible('#ribbon [data-skdone]') else None
        time.sleep(1)
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
