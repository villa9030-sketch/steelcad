r"""Prova di «Angoli tondi» (03/11, secondo giro): vaschetta 300 × 200 sp. 2 piegata a 30 sui 4 bordi; «Angoli tondi»
nella barra, si apre sullo sviluppo con i cerchi sugli 8 spigoli vivi; R5, anteprima; poi «Solo quelli che clicco»
togliendone due; Fatto. Poi il pezzo piegato.

    <python con playwright> tools\prova_ui_angoli_sviluppo.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando, comando_visibile  # noqa: F401  (comandi della barra, anche in «Altro ▾»)

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
            api('piega_bordi', 'SM1', [{'kind': 'edge', 'ref': f'L{i}'} for i in range(1, 5)], {'length': '30'}, 'aperti')
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            comando(pg, '[data-rbody="lamiera"] [data-azione="angoli_tondi"]')
            pg.wait_for_selector('#ag-corpo', timeout=20000)
            time.sleep(1.0)
            ok('8 cerchi sugli spigoli vivi', pg.locator('.ag-angolo').count() == 8)
            pg.locator('#ag-valore').fill('8')
            pg.locator('#ag-valore').dispatch_event('input')
            pg.wait_for_function("document.querySelector('.ant-stato.ok') && !document.querySelector('.ant-stato.calcolo')", timeout=60000)
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '01_tutti_r8.png'))
            # due angoli lasciati vivi col clic sui cerchi
            pg.locator('.ag-angolo').nth(0).click()
            pg.locator('.ag-angolo').nth(1).click()
            time.sleep(0.3)
            ok('scelti 6 di 8', 'Scelti 6 di 8' in pg.locator('#ag-corpo').inner_text())
            pg.wait_for_function("document.querySelector('.ant-stato.ok') && !document.querySelector('.ant-stato.calcolo')", timeout=60000)
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '02_sei_scelti.png'))
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(2.0)
            pg.screenshot(path=str(SHOTS / '03_sviluppo_fatto.png'))
            ok('nessun cerchio rimasto a video', pg.locator('.ag-angolo').count() == 0)
            ok('nell’albero «Angoli R8»', 'Angoli R8' in pg.locator('#tree').inner_text())
            comando(pg, '[data-rbody="lamiera"] [data-cmd="unfold"]')
            time.sleep(2.0)
            pg.get_by_text('Iso', exact=True).first.click()
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '04_piegato.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
