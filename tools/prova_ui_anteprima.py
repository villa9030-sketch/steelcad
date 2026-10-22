"""Prova dell'interfaccia: l'anteprima dei comandi (22/10) — Fai i tubi, lamiera dal contorno, piega su linea, gradino:
finestra di lato, risultato in azzurro, errore in rosso, sparisce alla chiusura.

    python tools/prova_ui_anteprima.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5185', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1400, 'height': 850}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.add_init_script("try { localStorage.setItem('steelcad.tema', 'scuro'); } catch {}")
        pg.goto('http://127.0.0.1:5185/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        ricarica = lambda: (pg.reload(), pg.wait_for_function('window.__steelcad && window.__steelcad.ready'), time.sleep(2),
                            pg.is_visible('#home-close') and pg.click('#home-close'), time.sleep(0.3))
        anteprima_ok = lambda: 'azzurro' in pg.inner_text('#modal-box .ant-stato')
        # 1. Fai i tubi
        api('new_project', 'disegno', {'name': 'Portale', 'piano': 'XZ'})
        api('sketch_add_polyline', 'S1', [[0, 0], [0, 900], [1500, 900], [1500, 0]], False)
        ricarica()
        pg.click('#tree .node:has-text("Sagoma") >> nth=0'); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
        pg.click('[data-make="tubi"]'); time.sleep(3)
        chk('tubi: finestra di lato e anteprima', pg.evaluate("document.getElementById('modal').classList.contains('laterale')") and anteprima_ok())
        pg.screenshot(path=str(OUT / '1_tubi.png'))
        pg.fill('#ft-p', 'boh'); time.sleep(2.5)
        chk('tubi: errore in rosso', pg.evaluate("document.querySelector('#modal-box .ant-stato').classList.contains('no')"))
        pg.click('#m-no'); time.sleep(0.5)
        chk('chiusa: anteprima via', pg.evaluate("!document.getElementById('modal').classList.contains('laterale')"))
        # 2. lamiera dal contorno
        api('new_project', 'zero', {'name': 'Staffa'}); api('sketch_add_rectangle', 'S1', [0, 0], [300, 200])
        ricarica()
        pg.click('#tree .node:has-text("Contorno") >> nth=0'); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
        pg.click('[data-make="sheet"]'); time.sleep(3)
        chk('lamiera dal contorno: anteprima', anteprima_ok())
        pg.screenshot(path=str(OUT / '2_lamiera.png'))
        pg.fill('#m-r', '2'); pg.fill('#m-k', '0,4'); pg.click('#m-ok'); time.sleep(3)
        chk('lamiera creata', api('state').get('sheet') is not None)
        # 3. gradino su una piega
        fid = api('state')['sheet']['data']['feature']
        api('add_flange', fid, 'L1', {'length': '40'})
        ricarica()
        pg.evaluate("window.__steelcad.select('flange=" + fid + "/FL1')"); time.sleep(1.2)
        pg.evaluate("document.querySelectorAll('#props details').forEach(d => d.open = true)")
        if pg.is_visible('#t-gradino'):
            pg.click('#t-gradino'); time.sleep(5)
            chk('gradino: anteprima', anteprima_ok())
            pg.screenshot(path=str(OUT / '3_gradino.png'))
            pg.click('#m-no')
        else:
            chk('pulsante gradino', False)
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
