"""Prova dell'interfaccia dei sottoassiemi (05/11) nel browser senza finestra: «Ferma con plexi» (ferma plexi +
plexiglass nella scanalatura) salvato come assieme, poi messo nell'anta dell'ufficio con «Inserisci pezzo». Nell'albero
un blocco con l'icona dell'assieme e la freccetta (dentro i due pezzi); nel 3D il plexiglass resta di vetro; la
distinta per pezzi e per sottoassiemi; il pannello del blocco con «Apri il sottoassieme»; aperto e tornati.

    python tools/prova_ui_sottoassiemi.py [cartella_screenshot] [porta]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5266
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
for f, n in (('anta', 'ANTA UFFICIO'), ('ferma_plexi', 'FERMA PLEXI B'), ('plexi', 'PLEXIGLASS')):
    shutil.copy(ROOT / 'tests' / 'data' / 'vano' / f'{f}.steelcad', cart / f'{n}.steelcad')
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
        applica = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                   " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }")
        # il sottoassieme: ferma plexi + plexiglass nella scanalatura
        assert pg.evaluate(api, ['new_assembly_con_pezzi', ['Ferma con plexi', [{'path': str(cart / 'FERMA PLEXI B.steelcad')},
                                                                                {'path': str(cart / 'PLEXIGLASS.steelcad')}]]])['ok']
        sc = pg.evaluate(api, ['scene', []])
        clic = lambda iid: {'inst': iid, 'face': next(o for o in sc['objects'] if o['id'] == iid)['faces'][0]['index']}  # noqa: E731
        assert pg.evaluate(api, ['asm_vano', [clic('I2'), clic('I1'), None, False]])['ok']
        assert pg.evaluate(api, ['save', [True]])['ok']
        sotto = next(cart.glob('*.steelcad-asm'))
        # l'anta, e dentro il sottoassieme
        r = pg.evaluate(applica, ['new_assembly_con_pezzi', ['Anta', [{'path': str(cart / 'ANTA UFFICIO.steelcad')}]]])
        r = pg.evaluate(applica, ['asm_insert', [str(sotto)]])
        ok('il sottoassieme entra con «Inserisci pezzo»', r is True)
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
        nodo = pg.query_selector('#tree .node[data-ref="I2"][data-kind="instance"]')
        ok('nell’albero: il blocco con l’icona dell’assieme', nodo is not None and 'data-ico="assieme"' in nodo.inner_html())
        ok('… e la freccetta per aprirlo', nodo is not None and nodo.query_selector('.freccia') is not None)
        nodo.query_selector('.freccia').click(); time.sleep(0.4)
        dentro = [x.inner_text() for x in pg.query_selector_all('#tree .node[data-kind="sottopezzo"]')]
        ok('aperto: i due pezzi dentro', dentro == ['FERMA PLEXI B', 'PLEXIGLASS'])
        trasp = pg.evaluate("""() => { const o = window.__steelcad.objs.get('I2'); const m = o.mesh.material;
            return Array.isArray(m) ? m.filter(x => x.visible !== false).map(x => x.transparent && x.opacity < 0.5) : null; }""")
        ok('nel 3D il plexiglass resta di vetro, il ferma plexi no', trasp == [False, True])
        pg.screenshot(path=str(out / 'so1_albero.png'))
        # la distinta
        pg.click('[data-tab="bom"]'); time.sleep(0.4)
        t = pg.inner_text('#tab-bom')
        ok('distinta per pezzi: anta, ferma plexi, plexiglass', all(x in t for x in ('ANTA UFFICIO', 'FERMA PLEXI B', 'PLEXIGLASS')))
        pg.click('#tab-bom [data-dist="gruppi"]'); time.sleep(0.3)
        t = pg.inner_text('#tab-bom')
        ok('per sottoassiemi: il blocco S2 con i suoi pezzi sotto', 'S2' in t and 'Ferma con plexi' in t and 'S2.1' in t and 'S2.2' in t)
        pg.screenshot(path=str(out / 'so2_distinta.png'))
        # il pannello del blocco
        pg.click('#tree .node[data-ref="I2"][data-kind="instance"] .lb'); time.sleep(0.8)
        ok('niente finitura per il blocco', not pg.query_selector('#a-fin'))
        ok('«Apri il sottoassieme» nella barretta', pg.is_visible('#mini-barra button:has-text("Apri il sottoassieme")'))
        pg.screenshot(path=str(out / 'so3_pannello.png'))
        pg.click('#mini-barra button:has-text("Apri il sottoassieme")')
        pg.wait_for_function("window.__steelcad.state.name === 'Ferma con plexi'", timeout=15000)
        time.sleep(0.6)
        ok('aperto il sottoassieme, col pulsante per tornare', pg.is_visible('#b-back'))
        pg.screenshot(path=str(out / 'so4_aperto.png'))
        pg.click('#b-back')
        pg.wait_for_function("window.__steelcad.state.name === 'Anta'", timeout=15000)
        ok('tornati all’anta', pg.evaluate("window.__steelcad.objs.size") == 2)
        ok('nessun errore nella pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
sys.exit(0 if all(esiti) else 1)
