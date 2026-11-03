r"""Il telaio di Stefano (807 × 725 × 795, 30×30×2) dall'inizio, come lo farebbe lui: home → Banco → misure → Dividi
(barra) tre volte; conta i passi e salva una foto per passo.

    .venv\Scripts\python.exe tools\prova_ui_tubi_dividi.py cartella_foto [porta]
"""
import os, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
SP.mkdir(parents=True, exist_ok=True)
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5263
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(PY), str(ROOT / 'app/dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
passi = []
n = [0]
def passo(cosa, foto=True):
    passi.append(cosa); n[0] += 1
    print(f'PASSO {n[0]:2d} {cosa}', flush=True)
    if foto:
        time.sleep(0.4); pg.screenshot(path=str(SP / f'{n[0]:02d}.png'))
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []
        pg.on('pageerror', lambda e: err.append(str(e))); pg.on('console', lambda m: m.type == 'error' and err.append(m.text + ' ' + str(m.location)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
        api = lambda nm, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [nm, list(a)])
        time.sleep(1)
        pg.evaluate("window.__steelcad.nuovo('telaio')"); time.sleep(1); passo('Nuovo → Banco')
        for k, v in (('L', '807'), ('P', '725'), ('H', '795'), ('ripiano', '0'), ('profilo', '30x30x2'), ('gambe', '30x30x2')):
            pg.fill(f'[data-f="{k}"]', v)
            passo(f'scrive {k} = {v}', foto=False)
        pg.screenshot(path=str(SP / 'dialogo.png'))
        pg.click('text=Crea banco'); time.sleep(4); passo('Crea banco')

        def clic_punto(xyz):
            xy = pg.evaluate("p => window.__steelcad.toScreen(p)", xyz)
            box = pg.locator('#c3d').bounding_box()
            pg.mouse.move(box['x'] + xy[0], box['y'] + xy[1]); time.sleep(0.3)
            pg.mouse.click(box['x'] + xy[0], box['y'] + xy[1]); time.sleep(1.8)
        # 1. croce sopra
        pg.click('.rb[data-azione="dividi"]'); time.sleep(0.5); passo('barra: Dividi')
        clic_punto([400, 15, 795]); time.sleep(1.5); passo('clic sul tubo davanti in alto (pannello Dividi, anteprima 2×2)')
        pg.click('#dv-ok'); time.sleep(3); passo('Dividi')
        # 2. fianchi
        pg.click('.rb[data-azione="dividi"]'); time.sleep(0.5); passo('barra: Dividi')
        clic_punto([807, 200, 780]); time.sleep(1.5); passo('clic sul fianco a destra in alto')
        if 'on' not in (pg.get_attribute('[data-dvf="destra"]', 'class') or ''):
            pg.click('[data-dvf="destra"]'); time.sleep(1.5); passo('sceglie «Il fianco a destra»')
        pg.check('#dv-chiudi'); time.sleep(2.5); passo('spunta «tubo a terra»')
        pg.click('#dv-ok'); time.sleep(3); passo('Dividi')
        # 3. traverso a 265 da terra, dietro
        pg.click('.rb[data-azione="dividi"]'); time.sleep(0.5); passo('barra: Dividi')
        clic_punto([795, 725, 650]); time.sleep(1.5); passo('clic sulla gamba dietro a destra')
        if 'on' not in (pg.get_attribute('[data-dvf="dietro"]', 'class') or ''):
            pg.click('[data-dvf="dietro"]'); time.sleep(1); passo('sceglie «Il dietro»')
        pg.click('[data-dvu="1"]'); time.sleep(0.6); passo('Montanti: No')
        pg.click('[data-dvv="mis"]'); time.sleep(0.6); passo('Traversi: A misura')
        assert not pg.is_checked('#dv-opp')            # davanti e dietro: «uguale anche…» non è spuntato
        pg.click('[data-dvr="bordo"]'); time.sleep(0.6); passo('la misura arriva al bordo')
        pg.fill('#dv-mv', '265'); time.sleep(2.5); passo('scrive 265')
        pg.press('#dv-mv', 'Enter'); time.sleep(3); passo('Invio')
        st = api('state')
        print('avvisi', st.get('warnings'))
        print('distinta', [(r_.get('length_mm'), r_.get('qty')) for r_ in (st.get('cutlist') or {}).get('rows', [])])
        print('errori', err)
        print('PASSI', len(passi))
        b.close()
finally:
    srv.kill()
