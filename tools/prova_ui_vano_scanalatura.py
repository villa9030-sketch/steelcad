"""Prova dell'interfaccia di «Metti nel vano» con una scanalatura (05/11): il ferma plexi (lamiera piegata con la
scanalatura alta 16 su tre lati, il quarto senza) e il plexiglass 913 × 913 sp. 16 (tests/data/vano). Clic sul
plexiglass, clic sul ferma plexi → nella scanalatura, posato sulla battuta, 0,5 mm per lato, «aperto» dietro;
l'avviso dei raggi delle pieghe; Fatto → tre accoppiamenti. Screenshot nella cartella.

    python tools/prova_ui_vano_scanalatura.py [cartella_screenshot] [porta]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando  # noqa: F401  (comandi della barra, anche nei menu)

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5264
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'ferma_plexi.steelcad', cart / 'FERMA PLEXI B.steelcad')
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'plexi.steelcad', cart / 'PLEXIGLASS.steelcad')
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
        pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                    ['Ferma plexi', [{'path': str(cart / 'FERMA PLEXI B.steelcad')}, {'path': str(cart / 'PLEXIGLASS.steelcad')}]])
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")

        def centro(iid, dx=0.0):
            return pg.evaluate("""([iid, dx]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const b = new T.Box3().setFromObject(o.mesh), c = b.getCenter(new T.Vector3());
                c.x = b.min.x + (b.max.x - b.min.x) * (0.5 + dx);
                const q = c.project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, dx])

        def clic_pezzo(iid):
            """Un punto sullo schermo dove il clic prende proprio quel pezzo (il ferma plexi è una cornice: il centro è vuoto)."""
            for dx in (0.0, -0.49, 0.49, -0.45, 0.45):
                x, y = centro(iid, dx)
                preso = pg.evaluate("""([x, y]) => { const S = window.__steelcad, T = S.THREE, r = document.querySelector('#c3d').getBoundingClientRect();
                    const rc = new T.Raycaster(); rc.setFromCamera(new T.Vector2((x - r.left) / r.width * 2 - 1, -(y - r.top) / r.height * 2 + 1), S.camera);
                    const h = rc.intersectObjects([...S.objs.values()].map(o => o.mesh), false)[0];
                    return h ? h.object.userData.id : null; }""", [x, y])
                if preso == iid:
                    return x, y
            raise RuntimeError(f'non trovo dove cliccare {iid}')

        comando(pg, '[data-asm-tool="vano"]')
        x, y = clic_pezzo('I2'); pg.mouse.click(x, y); time.sleep(0.4)
        x, y = clic_pezzo('I1'); pg.mouse.click(x, y)
        pg.wait_for_selector('#vano .pc-corpo', timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'sc1_anteprima.png'))
        t = pg.inner_text('#vano')
        ok('nella scanalatura da 16', 'Nella scanalatura' in t and 'Alta 16 mm' in t)
        ok('posato sulla battuta di sotto', 'battuta di sotto' in t)
        ok('gioco 0,5 ai lati, dietro aperto', 'sinistra 0,5' in t and 'destra 0,5' in t and 'davanti 0,5' in t and 'dietro aperto' in t)
        ok('avviso: lo spigolo nei raggi delle pieghe', 'raggi delle pieghe' in t and '0,13' in t)
        ok('niente scelte di profondità (non passa da parte a parte)', not pg.query_selector('#vano [data-prof]'))
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('in anteprima: x 2,5, y 2,5, z 2', abs(m[3] - 2.5) < 1e-3 and abs(m[7] - 2.5) < 1e-3 and abs(m[11] - 2) < 1e-3)
        pg.click('#vn-ok')
        pg.wait_for_function("!window.__vano.stato().el", timeout=10000)
        time.sleep(1.5)
        pg.screenshot(path=str(out / 'sc2_fatto.png'))
        ok('tre accoppiamenti nell’albero', pg.evaluate("JSON.stringify(window.__steelcad.state.tree)").count('"kind":"mate"') == 3)
        ok('messaggio: scanalatura e avviso', 'scanalatura da 16 mm' in pg.inner_text('body'))
        ok('nessun errore nella pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
sys.exit(0 if all(esiti) else 1)
