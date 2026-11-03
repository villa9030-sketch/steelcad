r"""Prova di «Sposta o cambia i fori» (03/11, secondo giro): piastra 200 × 100 con 4 fori Ø10 a 20 dai bordi fatti col
comando Foro; clic su un foro, «Sposta o cambia questi fori…», la finestra si riapre con 4 agli angoli a 20, scrivo 30,
anteprima, Fatto: i fori vanno a 30 dai bordi nello stesso taglio.

    <python con playwright> tools\prova_ui_foro_cambia.py cartella_screenshot [porta]
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
            api('new_project', 'lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1.5, 'k': 0.4})
            api('fori_guidati', 'SM1/sopra', {'tipo': 'tondo', 'd': 10, 'disposizione': 'angoli', 'bordo': 20})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            canvas = pg.locator('#c3d').bounding_box()
            x, y = pg.evaluate(CENTRO_FACCIA, ['TG1/parete'])
            pg.mouse.click(canvas['x'] + x, canvas['y'] + y)
            pg.wait_for_selector('.scheda-foro [data-a="cambia"]', timeout=15000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '01_clic_sul_foro.png'))
            ok('scheda del foro: «Sposta o cambia…»', 'Sposta o cambia' in pg.locator('.scheda-foro').inner_text())
            pg.locator('.scheda-foro [data-a="cambia"]').click()
            pg.wait_for_selector('#fo-bordo', timeout=15000)
            time.sleep(0.5)
            ok('si riapre con 4 agli angoli a 20', pg.locator('#fo-bordo').input_value() == '20'
               and 'on' in (pg.locator('[data-fo-seg="disposizione"] [data-v="angoli"]').get_attribute('class') or ''))
            ok('titolo «Cambia i fori»', 'Cambia i fori' in pg.locator('#fo-tit').inner_text())
            pg.screenshot(path=str(SHOTS / '02_finestra_riaperta.png'))
            pg.locator('#fo-bordo').fill('30')
            pg.locator('#fo-bordo').dispatch_event('input')
            pg.locator('#fo-d').fill('12')
            pg.locator('#fo-d').dispatch_event('input')
            pg.wait_for_function("document.getElementById('fo-frase')?.textContent.includes('Ø12')", timeout=30000)
            time.sleep(0.6)
            pg.screenshot(path=str(SHOTS / '03_anteprima_a_30.png'))
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '04_fori_spostati.png'))
            r = api('fori_da_modificare', 'TG1')
            ok('nel taglio di prima: 4 agli angoli a 30, Ø12', r.get('ok') and str(r['spec'].get('bordo')) == '30' and str(r['spec'].get('d')) == '12')
            albero = pg.locator('#tree').inner_text()
            ok('un taglio solo nell’albero', albero.count('Fori') == 1)
            print(albero)
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
