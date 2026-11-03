r"""Prova di «Piega i bordi» (03/11, secondo giro): la vaschetta. Lamiera 300 × 200 sp. 2, «Piega» nella barra,
clic sul bordo davanti, poi «Tutti i bordi del contorno», altezza 30, angoli chiusi, anteprima, Fatto; poi lo sviluppo.

    <python con playwright> tools\prova_ui_pieghe_bordi.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5262
CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'

CENTRO_FACCIA = """([nome]) => {
  // un punto della faccia che si vede davvero (il raggio dalla camera la colpisce per prima): il più vicino al centro
  const sc = window.__steelcad, T = sc.THREE, o = sc.objs.get('body');
  const f = o.data.faces.find(x => x.name === nome);
  const g = o.mesh.geometry, pos = g.attributes.position, idx = g.index.array;
  const pts = [];
  let cx = 0, cy = 0, cz = 0;
  for (let i = f.start; i < f.start + f.count; i += 3) {
    const p = new T.Vector3();
    for (let k = 0; k < 3; k++) p.add(new T.Vector3(pos.getX(idx[i + k]), pos.getY(idx[i + k]), pos.getZ(idx[i + k])));
    p.divideScalar(3).applyMatrix4(o.mesh.matrixWorld); pts.push([p, i]); cx += p.x; cy += p.y; cz += p.z;
  }
  const c = new T.Vector3(cx / pts.length, cy / pts.length, cz / pts.length);
  pts.sort((a, b) => a[0].distanceTo(c) - b[0].distanceTo(c));
  const ray = new T.Raycaster(), cv = document.getElementById('c3d');
  for (const [p, i] of pts) {
    const [x, y] = sc.toScreen(p.toArray());
    ray.setFromCamera(new T.Vector2(x / cv.clientWidth * 2 - 1, -(y / cv.clientHeight) * 2 + 1), sc.camera);
    const h = ray.intersectObject(o.mesh, false)[0];
    if (h && h.faceIndex * 3 >= f.start && h.faceIndex * 3 < f.start + f.count) return [x, y];
  }
  return sc.toScreen(c.toArray());
}"""


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    env = dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart))
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1500, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            api = lambda nome, *a: pg.evaluate("([n, a]) => fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())", [nome, list(a)])  # noqa: E731
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            api('new_project', 'lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            canvas = pg.locator('#c3d').bounding_box()
            # dalla barretta del bordo: «Piega anche altri bordi»
            x, y = pg.evaluate("""() => { const sc = window.__steelcad, e = sc.bendEdges.find(x => x.ref === 'L2');
                return sc.toScreen(e.a.map((v, i) => (v + e.b[i]) / 2)); }""")
            pg.mouse.move(canvas['x'] + x, canvas['y'] + y)
            time.sleep(0.3)
            pg.mouse.click(canvas['x'] + x, canvas['y'] + y)
            pg.wait_for_selector('#mini-barra button[aria-label^="Piega anche altri bordi"]', timeout=10000)
            pg.locator('#mini-barra button[aria-label^="Piega anche altri bordi"]').hover()
            time.sleep(1.2)
            pg.screenshot(path=str(SHOTS / '00_barretta_bordo.png'))
            pg.locator('#mini-barra button[aria-label^="Piega anche altri bordi"]').click()
            pg.wait_for_selector('#pg-corpo', timeout=10000)
            ok('dalla barretta: la finestra col bordo a destra già scelto', pg.locator('.pg-bordo').count() == 1 and 'destra' in pg.locator('.pg-bordi').inner_text())
            pg.locator('#m-no').click()
            time.sleep(0.5)
            pg.locator('[data-rbody="lamiera"] [data-cmd="flange_help"]').click()
            pg.wait_for_selector('#pg-corpo', timeout=10000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '01_piega_aperta.png'))
            # clic sul bordo davanti (L1), dal suo punto a metà sullo schermo
            x, y = pg.evaluate("""() => { const sc = window.__steelcad, e = sc.bendEdges.find(x => x.ref === 'L1');
                return sc.toScreen(e.a.map((v, i) => (v + e.b[i]) / 2)); }""")
            pg.mouse.move(canvas['x'] + x, canvas['y'] + y)
            time.sleep(0.3)
            pg.mouse.click(canvas['x'] + x, canvas['y'] + y)
            time.sleep(0.5)
            ok('un bordo scelto col clic', pg.locator('.pg-bordo').count() == 1 and 'davanti' in pg.locator('.pg-bordi').inner_text())
            pg.wait_for_selector('.ant-stato.ok', timeout=30000)
            pg.screenshot(path=str(SHOTS / '02_un_bordo_anteprima.png'))
            pg.locator('#pg-tutti').click()
            time.sleep(0.4)
            ok('tutti e 4 i bordi', pg.locator('.pg-bordo').count() == 4)
            pg.locator('#pg-length').fill('30')
            pg.locator('#pg-length').dispatch_event('input')
            pg.locator('[data-pg-seg="angoli"] [data-v="chiusi"]').click()
            time.sleep(0.3)
            ok('gioco nell’angolo 0,5', pg.locator('#pg-gioco').input_value() == '0,5')
            pg.wait_for_function("document.querySelector('.ant-stato.ok') && !document.querySelector('.ant-stato.calcolo')", timeout=60000)
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '03_vaschetta_anteprima.png'))
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            pg.wait_for_function("window.__steelcad.state.sheet && window.__steelcad.state.sheet.flanges === 4", timeout=60000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '04_vaschetta_fatta.png'))
            st = pg.evaluate('window.__steelcad.state')
            ok('nella storia: «Pieghe su 4 bordi»', 'Pieghe su 4 bordi' in st['storia']['passi'])
            pg.locator('[data-rbody="lamiera"] [data-cmd="unfold"]').click()
            time.sleep(2.0)
            pg.screenshot(path=str(SHOTS / '05_sviluppo.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
