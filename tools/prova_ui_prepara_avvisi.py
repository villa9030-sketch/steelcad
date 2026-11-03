"""Prova (03/11, terzo giro): «Prepara» di un assieme con un pezzo in lamiera che ha un'estrusione fatta dopo la
lamiera: l'avviso pezzo per pezzo prima di salvare; poi le tavole dell'assieme con «2 pz» e lo specchiato nel titolo.

    python tools/prova_ui_prepara_avvisi.py CARTELLA_FOTO [porta]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
W = Path(__file__).resolve().parents[1]; PY = sys.executable; sys.path.insert(0, str(W))
from playwright.sync_api import sync_playwright
from app.service import Service
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[2] if len(sys.argv) > 2 else '5270'
tmp = Path(tempfile.mkdtemp())


def pezzo(nome, boss=False):
    s = Service()
    s.new_project('lamiera', {'name': 'Lamiera', 'larghezza': 300, 'profondita': 150, 'spessore': 2, 'raggio': 2, 'k': 0.4})
    assert s.add_flange('SM1', 'L1', {'length': '40'})['ok']
    if boss:
        def fn():
            sk = s.doc.add_sketch('XY', 'boss')
            p = [sk.point(*q) for q in ((10, 10), (40, 10), (40, 40), (10, 40))]
            for a, b in zip(p, p[1:] + p[:1]):
                sk.line(a, b)
            s.doc.add_feature('extrude', 'Estrusione', sketch=sk.id, operation='add', distance=20)
        assert s._change('Estrusione', fn)['ok']
    p = tmp / f'{nome}.steelcad'
    assert s.save(str(p))['ok']
    return p


a, b, c = pezzo('Staffa'), pezzo('Staffa specchiato'), pezzo('Supporto motore', boss=True)
s = Service()
s.new_assembly('Banco prova')
for p in (a, a, b, b, c):
    assert s.asm_insert(str(p))['ok']
asm = tmp / 'Banco prova.steelcad-asm'
assert s.save(str(asm))['ok']
srv = subprocess.Popen([PY, str(W / 'app/dev_server.py'), '--porta', PORTA, '--cartella', str(tmp)], cwd=str(W),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp)))
while not srv.stdout.readline().startswith(b'http'): pass
try:
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = br.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *x: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(x)])
        print('apri', api('open_path', str(asm)).get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000); time.sleep(3)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.click('#b-prepara'); time.sleep(3)
        pg.screenshot(path=str(OUT / '1_prepara_avvisi.png'))
        print('avviso', pg.inner_text('#modal-box .prep-avvisi') if pg.is_visible('#modal-box .prep-avvisi') else None)
        pg.click('#prep-tavole'); pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=90000); time.sleep(1.5)
        pg.screenshot(path=str(OUT / '2_tavole.png'))
        pg.locator('#tav-ed', has_text='sviluppo').locator('text=sviluppo').nth(0).click(); time.sleep(1.5)
        pg.screenshot(path=str(OUT / '3_sviluppo_staffa.png'))
        print('errori pagina', err)
        br.close()
finally:
    srv.kill()
