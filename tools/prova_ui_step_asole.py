"""Prova dell'interfaccia: STEP di una vaschetta con asole attraverso le pieghe (05/11). Si apre come lamiera da
STEP: 4 pieghe (non 7), le asole fori dello sviluppo, lo sviluppo largo quanto quello di Radius. Foto del pezzo, dello
sviluppo in tema chiaro e scuro, e di una vaschetta ad angoli chiusi.

    python tools/prova_ui_step_asole.py [cartella_foto] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5323
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'


def vasca(chiusi=False, asole=()):
    from app.service import Service
    s = Service()
    s.new_project('lamiera', {'name': 'Vaschetta', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.33})
    for e in ('L1', 'L2', 'L3', 'L4'):
        s.add_flange('SM1', e, {'length': 40})
    if chiusi:
        fl = [f['id'] for f in s._sheet_def('SM1')['flanges']]
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            s.set_corner('SM1', fl[a], fl[b], 'over', 0)
    if asole:
        sid = s.sketch_on_flat('SM1')['sketch']
        for a, b in asole:
            s.sketch_add_rectangle(sid, a, b)
        assert s.create_from_sketch(sid, 'cut', {})['ok']
    return s


v = vasca(asole=[([30, -10], [40, 8]), ([70, -10], [80, 8]), ([292, 55], [310, 65])])
ATTESO = v.result.body.sheet.flat_size
SP = cart / 'vaschetta asolata.step'
assert v.export_step(str(SP))['ok']
c = vasca(chiusi=True)
ATTESO_C = c.result.body.sheet.flat_area
SC = cart / 'vaschetta angoli chiusi.step'
assert c.export_step(str(SC))['ok']

env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
while not srv.stdout.readline().startswith(b'http'):
    pass
esiti = []


def ok(t, cond):
    esiti.append(bool(cond))
    print(('OK   ' if cond else 'NO   ') + t, flush=True)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))

        def apri():
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        apri()
        applica = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                   " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r; }")
        r = pg.evaluate(applica, ['import_step', [str(SP), '0,33']])
        ok(f'STEP con le asole aperto: {str(r.get("message"))[:110]}', r.get('ok'))
        time.sleep(1.0)
        st = pg.evaluate('window.__steelcad.state')
        dati = (st.get('sheet') or {}).get('data', {})
        righe = dati.get('bend_rows') or []
        ok(f'4 pieghe nella tabella (non una per pezzo di piega): {len(righe)}', len(righe) == 4)
        ok('le pieghe lunghe sono lunghe 292 (tutta la piega)', sorted(round(x['length']) for x in righe) == [192, 192, 292, 292])
        misure = r.get('message', '')
        ok('lo sviluppo è largo quanto quello di Radius',
           f'{ATTESO[0]:.1f}'.replace('.', ',') in misure and f'{ATTESO[1]:.1f}'.replace('.', ',') in misure)
        ok('le asole sono fori dello sviluppo (contorno + 3)', len(dati.get('outline') or []) >= 4)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8); pg.mouse.move(5, 895)
        pg.screenshot(path=str(out / '1_vaschetta_asolata_3d.png'))
        pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(1.2); pg.mouse.move(5, 895)
        pg.screenshot(path=str(out / '2_sviluppo_asole.png'))
        # tema scuro
        imp = "async (t) => fetch('/api/set_impostazioni', {method: 'POST', body: JSON.stringify([{tema: t}])})"
        pg.evaluate(imp, 'scuro')
        apri()
        pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(1.2); pg.mouse.move(5, 895)
        ok('tema scuro', pg.evaluate("document.body.classList.contains('dark')"))
        pg.screenshot(path=str(out / '3_sviluppo_asole_scuro.png'))
        pg.evaluate(imp, 'chiaro')
        apri()
        # vaschetta ad angoli chiusi
        r = pg.evaluate(applica, ['import_step', [str(SC), '0,33']])
        ok(f'STEP ad angoli chiusi aperto: {str(r.get("message"))[:110]}', r.get('ok'))
        area = pg.evaluate("async () => (await (await fetch('/api/state', {method: 'POST', body: '[]'})).json())")
        fa = ((area.get('state') or area).get('sheet') or {}).get('data', {}).get('flat_area')
        ok(f'angoli chiusi: area dello sviluppo {fa} come quella di Radius {ATTESO_C:.1f}', fa is not None and abs(fa - ATTESO_C) < 1)
        pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(1.2); pg.mouse.move(5, 895)
        pg.screenshot(path=str(out / '4_sviluppo_angoli_chiusi.png'))
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
