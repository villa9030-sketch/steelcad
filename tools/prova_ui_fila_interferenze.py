"""Prova dell'interfaccia di «In fila» e delle interferenze in rosso (03/11, secondo giro): piastra 300×200 sp. 8 e
staffa a L appoggiata contro il bordo di sinistra; dalla barretta «In fila», 3 a passo 100 (anteprima trasparente),
Invio → 3 staffe; una spinta dentro la piastra → «Interferenze»: il pezzo in comune in rosso col nome dei due pezzi.

    python tools/prova_ui_fila_interferenze.py [cartella_screenshot] [porta]
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
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5267
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
        api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
        aggiorna = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); return r; }")
        assert pg.evaluate(api, ['new_project', ['lamiera', {'name': 'Piastra base', 'larghezza': 300, 'profondita': 200, 'spessore': 8}]])['ok']
        assert pg.evaluate(api, ['save', [True]])['ok']
        assert pg.evaluate(api, ['crea_da_modello', ['staffa', {'nome': 'Staffa a L', 'larghezza': 100, 'profondita': 80, 'altezza': 80,
                                                                'spessore': 3, 'raggio': 3, 'k': 0.33}]])['ok']
        assert pg.evaluate(api, ['save', [True]])['ok']
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r; }",
                        ['Piastra con staffe', [{'path': str(cart / 'Piastra base.steelcad')}, {'path': str(cart / 'Staffa a L.steelcad')}]])
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'r1_assieme_creato.png'))
        ok('il messaggio dell’assieme dice «Appoggia»', 'Appoggia' in (r.get('message') or ''))

        def faccia(iid, nome):
            return {'inst': iid, 'face': pg.evaluate("([i, n]) => window.__steelcad.objs.get(i).data.faces.find(f => f.name === n).index", [iid, nome])}
        # la staffa contro il bordo di sinistra, al centro davanti/dietro
        r = pg.evaluate(aggiorna, ['asm_appoggia', [faccia('I2', 'SM1/sopra'), faccia('I1', 'SM1/sopra'),
                                                    {'u': {'modo': 'basso', 'mm': 0}, 'v': {'modo': 'centro'}}]])
        assert r['ok'], r
        time.sleep(1)
        # In fila: dalla barretta della staffa
        pg.click('#tree .node[data-kind="instance"][data-ref="I2"]'); time.sleep(0.8)
        ok('barretta: «In fila»', pg.is_visible('#mini-barra button[data-t="In fila"]'))
        pg.click('#mini-barra button[data-t="In fila"]')
        pg.wait_for_selector('#ripeti', timeout=5000); time.sleep(0.3)
        pg.fill('#rp-n', '3')
        pg.fill('#rp-p', '100'); time.sleep(0.6)
        ok('anteprima: 2 copie trasparenti', pg.evaluate('window.__ripeti.copie') == 2)
        print('   pannello:', pg.inner_text('#ripeti').replace('\n', ' | '))
        pg.screenshot(path=str(out / 'r2_in_fila_anteprima.png'))
        pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.objs.size === 4", timeout=20000); time.sleep(1.0)
        st = pg.evaluate('window.__steelcad.state')
        ok('3 staffe in fila: Staffa a L, (2), (3); in distinta 3', [i['name'] for i in st['instances']][1:] == ['Staffa a L', 'Staffa a L (2)', 'Staffa a L (3)']
           and next(b for b in st['bom'] if b['description'].startswith('Staffa'))['qty'] == 3)
        xs = [pg.evaluate(f"window.__steelcad.objs.get('I{k}').data.matrix[3]") for k in (2, 3, 4)]
        ok('a 0, 100, 200 da sinistra', [round(x) for x in xs] == [0, 100, 200])
        pg.screenshot(path=str(out / 'r3_in_fila_fatto.png'))
        # interferenze: la staffa di mezzo spinta dentro la piastra di 2 mm (l'accoppiamento di Appoggia a -2)
        m = next(m for m in pg.evaluate(api, ['state', []])['state']['tree']['children'] if m.get('label') == 'Accoppiamenti') \
            if False else None
        mid = pg.evaluate(api, ['select', ['I2']])['selection']['mates'][0]
        pg.evaluate(aggiorna, ['asm_edit_mate', [mid, {'offset': -2}]])
        time.sleep(0.8)
        pg.click('#ribbon [data-cmd="asm_interf"]')
        pg.wait_for_function("window.__interf.n > 0", timeout=20000); time.sleep(0.8)
        lab = pg.eval_on_selector_all('#interf-box .dim.interf', 'els => els.map(e => e.textContent)')
        print('   cartellini:', lab)
        ok('interferenze in rosso con i nomi dei due pezzi', len(lab) == 3 and all('Piastra base' in t and 'Staffa a L' in t for t in lab))
        pg.screenshot(path=str(out / 'r4_interferenze_rosse.png'))
        pg.evaluate(aggiorna, ['undo', []]); time.sleep(1.0)
        ok('cambiato l’assieme: il rosso sparisce', pg.evaluate('window.__interf.n') == 0)
        ok('nessun errore JavaScript', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.terminate()
print(f'{sum(esiti)}/{len(esiti)} ok; screenshot in {out}')
sys.exit(0 if all(esiti) else 1)
