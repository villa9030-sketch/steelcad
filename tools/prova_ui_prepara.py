"""Prova dell'interfaccia (03/11): «Prepara per il laser» con l'avviso sugli angoli quasi tondi, il link «Guarda le
tavole», la conferma che resta dopo «Salva i file» con «Apri la cartella» e «Guarda le tavole».

    python tools/prova_ui_prepara.py CARTELLA_FOTO
"""
import os, subprocess, tempfile, time, sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
srv = subprocess.Popen([PY, str(W / 'app/dev_server.py'), '--porta', '5264', '--cartella', str(tmp)], cwd=str(W),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp)))
while not srv.stdout.readline().startswith(b'http'): pass
def log(*a): print(*a, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5264/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        # collare storto (arco a clic)
        api('new_project', 'zero', {})
        api('sketch_add_polyline', 'S1', [[0, 0], [28, 0]], False); api('sketch_add_arc3', 'S1', [28, 0], [85, 55], [140, 0]); api('sketch_add_polyline', 'S1', [[140, 0], [168, 0]], False)
        r = api('create_from_sketch', 'S1', 'profilo', {'lunghezza': 30, 'spessore': 3, 'calandra': True, 'gira': True, 'raggio': 1, 'k': 0.4}); log('collare', r['ok'])
        api('save', str(tmp / 'Collare tubo 110.steelcad'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.click('#b-prepara'); time.sleep(2.5)
        pg.screenshot(path=str(OUT / '1_prepara.png'))
        pg.click('#modal-box [data-voce="officina"]'); time.sleep(0.3)
        pg.click('#m-ok'); time.sleep(4)
        pg.screenshot(path=str(OUT / '2_dopo_salva.png'))
        log('conferma resta', pg.is_visible('#prep-apri'))
        time.sleep(5); pg.screenshot(path=str(OUT / '3_dopo_10s.png'))
        pg.click('#prep-apri'); time.sleep(0.5)
        pg.click('#prep-tav'); pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(1)
        pg.screenshot(path=str(OUT / '4_tavole.png'))
        pg.locator('#tav-ed button', has_text='Chiudi').first.click(); time.sleep(0.8)
        pg.click('#b-prepara'); time.sleep(2.5)
        pg.click('#prep-tavole'); pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(1)
        pg.screenshot(path=str(OUT / '5_tavole_da_link.png'))
        log('errori pagina', err)
        b.close()
finally:
    srv.kill()
