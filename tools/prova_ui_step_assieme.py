"""Prova dell'interfaccia: lo STEP di un assieme si apre come assieme di Radius (29/10).

    python tools/prova_ui_step_assieme.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
# lo STEP di prova: una vasca, due staffe uguali, un perno
crea = r'''
import sys, build123d as bd
sys.path.insert(0, r"%s")
from app.service import Service
s1 = Service(); s1.esempio('staffa'); st = bd.Shape.cast(s1.result.body.shape)
s0 = Service(); s0.new_project('lamiera', {'name': 'V', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.33})
[s0.add_flange('SM1', e, {'length': 40}) for e in ('L1', 'L2', 'L3', 'L4')]
v = bd.Shape.cast(s0.result.body.shape)
bd.export_step(bd.Compound(label='Telaio', children=[bd.Compound(label='Vasca', children=[v]),
    bd.Compound(label='Staffa', children=[st.moved(bd.Location((0, -100, 0)))]),
    bd.Compound(label='Staffa', children=[st.moved(bd.Location((300, -100, 0), (0, 0, 1), 90))]),
    bd.Compound(label='Perno', children=[bd.Cylinder(10, 50).moved(bd.Location((150, 100, 60)))])]), r"%s")
''' % (ROOT, cart / 'telaio.step')
subprocess.run([str(ROOT / '.venv/Scripts/python.exe'), '-c', crea], check=True, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc0')))
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5208', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5208/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        pg.evaluate("window.__steelcad.hideHome()")
        # come fa il dialogo: lo STEP risponde «è un assieme» con l'elenco
        r = api('import_step', str(cart / 'telaio.step'), 0.33)
        chk(f'lo STEP è un assieme: {len(r.get("pezzi", []))} pezzi', r.get('code') == 'assieme')
        pg.evaluate("r => window.__stepPezzi(r)", r); time.sleep(0.5)
        chk('nella finestra c’è «Apri come assieme»', pg.is_visible('#sp-asm'))
        pg.screenshot(path=str(OUT / '1_elenco.png'))
        pg.click('#sp-asm'); pg.wait_for_function("window.__steelcad.state && window.__steelcad.state.mode === 'assembly'", timeout=60000); time.sleep(2)
        st = api('state')
        chk('si apre l’assieme: ' + ', '.join(f"{x['description'].split(',')[0]} ×{x['qty']}" for x in st['bom']), st['mode'] == 'assembly' and len(st['bom']) == 3)
        chk('i pezzi nella cartella accanto allo STEP', len(list((cart / 'telaio – pezzi').glob('*.steelcad'))) == 3)
        pg.screenshot(path=str(OUT / '2_assieme.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
