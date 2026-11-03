r"""Prova di «Incastri» dalla barra (03/11, secondo giro): U chiusa 200 × 100 sp. 2 (la punta dell'ultima piega appoggia
sulla base); «Incastri» nella barra, 3 linguette da 15, gioco 0,2, anteprima, Fatto.

    <python con playwright> tools\prova_ui_incastri.py cartella_screenshot [porta]
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
            api('new_project', 'lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})
            api('add_flange', 'SM1', 'L1', {'length': '40'})
            api('add_flange', 'SM1', None, {'length': '30'}, 'FL1')
            api('add_flange', 'SM1', None, {'length': '38'}, 'FL2')
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '00_barra.png'))
            pg.locator('[data-rbody="lamiera"] [data-azione="incastri"]').click()
            pg.wait_for_selector('#in-corpo', timeout=20000)
            pg.wait_for_function("document.querySelector('.ant-stato.ok') && !document.querySelector('.ant-stato.calcolo')", timeout=60000)
            time.sleep(0.8)
            ok('la finestra dice dove appoggia', 'faccia di sopra' in pg.locator('#in-corpo').inner_text())
            pg.screenshot(path=str(SHOTS / '01_incastri_anteprima.png'))
            pg.locator('#in-n').fill('20')
            pg.locator('#in-n').dispatch_event('input')
            pg.wait_for_selector('.ant-stato.no', timeout=60000)
            time.sleep(0.5)
            ok('20 linguette: rosso e il perché', 'non stanno' in pg.locator('.ant-stato').inner_text() and pg.locator('#m-ok').is_disabled())
            pg.screenshot(path=str(SHOTS / '02_troppe_rosso.png'))
            pg.locator('#in-n').fill('3')
            pg.locator('#in-n').dispatch_event('input')
            pg.wait_for_function("document.querySelector('.ant-stato.ok') && !document.querySelector('.ant-stato.calcolo')", timeout=60000)
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '03_incastri_fatti.png'))
            ok('nell’albero linguette e asole', 'Linguette di FL3' in pg.locator('#tree').inner_text() or 'inguett' in pg.locator('#tree').inner_text())
            print(pg.locator('#tree').inner_text())
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
