r"""Prova del comando «Foro» e «Asola» diretti sul pezzo (03/11), come una persona: staffa 200 × 100 sp. 3 piegata
a 60, «Foro» nella barra, Ø10,5, «4 agli angoli» a 20 dai bordi, anteprima, Fatto; poi clic sulla faccia piegata,
«Asola» dalla barretta, 30 × 10 al centro; poi «Dove clicco» con un clic sul pezzo.

    <python con playwright> tools\prova_ui_foro.py cartella_screenshot [porta]
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
            api('new_project', 'lamiera', {'larghezza': 200, 'profondita': 100, 'spessore': 3, 'raggio': 1.5, 'k': 0.4})
            api('add_flange', 'SM1', 'L1', {'length': '60'})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            canvas = pg.locator('#c3d').bounding_box()

            def clic_faccia(nome):
                x, y = pg.evaluate(CENTRO_FACCIA, [nome])
                pg.mouse.click(canvas['x'] + x, canvas['y'] + y)
                time.sleep(0.8)

            # 1) «Foro» nella barra in alto
            comando(pg, '[data-rbody="lamiera"] [data-azione="foro"]')
            pg.wait_for_selector('#fo-d', timeout=10000)
            time.sleep(0.6)
            pg.screenshot(path=str(SHOTS / '01_foro_aperto.png'))
            pg.keyboard.type('10,5')
            pg.locator('[data-fo-seg="disposizione"] [data-v="angoli"]').click()
            time.sleep(0.3)
            pg.keyboard.press('Control+A')
            pg.keyboard.type('20')
            pg.wait_for_function("document.getElementById('fo-frase')?.textContent.includes('4 fori')", timeout=30000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '02_quattro_fori_anteprima.png'))
            ok('anteprima: «Toglie dal pezzo: 4 fori Ø10,5»', '4 fori Ø10,5' in pg.locator('#fo-frase').inner_text())
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '03_fori_fatti.png'))

            # 2) asola sulla faccia piegata, dalla barretta
            clic_faccia('SM1/FL1/esterno')
            pg.screenshot(path=str(SHOTS / '04_barretta_faccia_piegata.png'))
            pg.locator('#mini-barra button[aria-label="Asola"]').click()
            pg.wait_for_selector('#fo-larg', timeout=10000)
            pg.keyboard.type('30')
            pg.locator('#fo-alt').fill('10')
            pg.locator('#fo-alt').dispatch_event('input')
            pg.locator('[data-fo-seg="disposizione"] [data-v="centro"]').click()
            try:
                pg.wait_for_function("document.getElementById('fo-frase')?.textContent.includes('asola') || document.querySelector('.ant-stato.no')", timeout=30000)
            except Exception:
                pg.screenshot(path=str(SHOTS / '05x_errore.png'))
                print(pg.locator('#modal-box').inner_text(), errori)
                raise
            print('stato:', pg.locator('#modal-box').inner_text())
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '05_asola_anteprima.png'))
            ok('titolo sulla faccia piegata', 'flangia' in pg.locator('#fo-tit').inner_text() or 'esterna' in pg.locator('#fo-tit').inner_text())
            pg.keyboard.press('Enter')
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '06_asola_fatta.png'))

            # 3) «Dove clicco»: clic sulla base
            pg.keyboard.press('Escape')
            comando(pg, '[data-rbody="lamiera"] [data-azione="foro"]')
            try:
                pg.wait_for_selector('#fo-d', timeout=20000)
            except Exception:
                pg.screenshot(path=str(SHOTS / '07x_errore.png'))
                print('ERR', errori)
                raise
            pg.keyboard.type('8')
            pg.locator('[data-fo-seg="disposizione"] [data-v="punti"]').click()
            time.sleep(0.3)
            clic_faccia('SM1/sopra')
            pg.wait_for_selector('[data-px="0"]', timeout=10000)
            pg.wait_for_function("document.getElementById('fo-frase')?.textContent.includes('foro')", timeout=30000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '07_dove_clicco.png'))
            ok('dove clicco: misura scritta', pg.locator('[data-px="0"]').input_value() != '')
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '08_dopo_dove_clicco.png'))
            albero = pg.locator('#tree').inner_text()
            print(albero)
            ok('albero: «Fori 4 × Ø10,5»', '4 × Ø10,5' in albero)
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
