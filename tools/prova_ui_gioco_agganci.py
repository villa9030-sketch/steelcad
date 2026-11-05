"""Prova dell'interfaccia di «Gioco» e dei punti di aggancio sulle facce piane (05/11, idee da SolidCraft) nel browser
senza finestra, col ferma plexi e il plexiglass (tests/data/vano):
- assieme coi due pezzi staccati: «Gioco», clic sulla faccia sopra del plexiglass e su quella del ferma plexi →
  pannello a destra, quota nel 3D, 50 mm tra i pezzi;
- plexiglass nella scanalatura: il gioco tra le due facce di fianco (0,5) e tra i pezzi interi (entrano: in rosso);
- Quota: col mouse sulla faccia sopra del plexiglass si vedono i suoi punti e il centro della faccia si aggancia;
- disegno sulla faccia di una lamiera: il centro della faccia tra gli agganci.
Screenshot nella cartella, anche col tema scuro.

    python tools/prova_ui_gioco_agganci.py [cartella_screenshot] [porta]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando, comando_visibile

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5305
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'ferma_plexi.steelcad', cart / 'FERMA PLEXI.steelcad')
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
# la faccia piana dell'istanza con la normale più vicina a n e, tra queste, la più in alto/avanti lungo n
FACCIA = """([iid, n, vicino]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid), P = o.data.positions, I = o.data.indices;
  const N = new T.Vector3(...n); let best = null;
  for (const f of o.data.faces) { const c = new T.Vector3(); let k = 0, ok = true;
    const a = new T.Vector3(P[I[f.start]*3], P[I[f.start]*3+1], P[I[f.start]*3+2]), b = new T.Vector3(P[I[f.start+1]*3], P[I[f.start+1]*3+1], P[I[f.start+1]*3+2]),
          d = new T.Vector3(P[I[f.start+2]*3], P[I[f.start+2]*3+1], P[I[f.start+2]*3+2]);
    const nn = b.clone().sub(a).cross(d.clone().sub(a)).normalize();
    if (nn.dot(N) < 0.999) continue;
    let area = 0;
    for (let j = f.start; j < f.start + f.count; j += 3) { const A = new T.Vector3(P[I[j]*3], P[I[j]*3+1], P[I[j]*3+2]),
      B = new T.Vector3(P[I[j+1]*3], P[I[j+1]*3+1], P[I[j+1]*3+2]), C = new T.Vector3(P[I[j+2]*3], P[I[j+2]*3+1], P[I[j+2]*3+2]);
      area += B.clone().sub(A).cross(C.clone().sub(A)).length() / 2; c.add(A).add(B).add(C); k += 3; }
    c.multiplyScalar(1 / k);
    const h = vicino ? -c.distanceTo(new T.Vector3(...vicino)) : c.dot(N) + area * 1e-9;
    if (!best || h > best.h + 1e-6 || (Math.abs(h - best.h) < 1e-6 && area > best.area)) best = { index: f.index, h, area, c: c.toArray() }; }
  return best; }"""
SCHERMO = """(p) => { const S = window.__steelcad, q = new S.THREE.Vector3(...p).project(S.camera), r = document.querySelector('#c3d').getBoundingClientRect();
  return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }"""
NEL_MONDO = """([iid, p]) => new window.__steelcad.THREE.Vector3(...p).applyMatrix4(window.__steelcad.objs.get(iid).mesh.matrixWorld).toArray()"""

try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        for tema in ('chiaro', 'scuro'):
            pg = b.new_page(viewport={'width': 1500, 'height': 900})
            err = []
            pg.on('pageerror', lambda e: err.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            if tema == 'scuro' and not pg.evaluate("document.body.classList.contains('dark')"):
                pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
            api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
            r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                            " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                            ['Ferma', [{'path': str(cart / 'FERMA PLEXI.steelcad')}, {'path': str(cart / 'PLEXIGLASS.steelcad')}]])
            pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
            pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
            pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
            suf = '' if tema == 'chiaro' else '_scuro'

            def clic_faccia(iid, n, dx=0.0, dy=0.0):
                f = pg.evaluate(FACCIA, [iid, n, None])
                w = pg.evaluate(NEL_MONDO, [iid, f['c']])
                x, y = pg.evaluate(SCHERMO, w)
                pg.mouse.move(x + dx, y + dy, steps=3); time.sleep(0.25); pg.mouse.click(x + dx, y + dy); time.sleep(0.4)
                return f

            # ---- 1. il gioco tra i due pezzi staccati (50 mm)
            if tema == 'chiaro':
                ok('pulsante «Gioco» nella barra dell’assieme, vicino a Interferenze', comando_visibile(pg, '[data-asm-tool="gioco"]'))
            comando(pg, '[data-asm-tool="gioco"]')
            ok('Gioco acceso, suggerimento in basso', 'Gioco (1 di 2)' in (pg.get_attribute('#sk-help', 'title') or ''))
            clic_faccia('I2', [0, 0, 1], 0, 0)                 # sopra il plexiglass
            ok('poi chiede l’altra faccia', 'Gioco (2 di 2)' in (pg.get_attribute('#sk-help', 'title') or ''))
            clic_faccia('I1', [0, 0, 1], 0, 0)                 # sopra il ferma plexi
            pg.wait_for_selector('#gioco-pan', timeout=15000); time.sleep(0.5)
            t = pg.inner_text('#gioco-pan')
            ok(f'pannello: tra i pezzi 50 mm ({t.splitlines()[-3:]})', '50 mm' in pg.inner_text('#gc-pezzi'))
            et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
            ok(f'quote nel 3D: {et}', any(e.startswith('gioco') for e in et) and '50 tra i pezzi' in et)
            ok('il comando resta acceso per altri due', 'Gioco (1 di 2)' in (pg.get_attribute('#sk-help', 'title') or ''))
            pg.screenshot(path=str(out / f'g1_staccati{suf}.png'))
            pg.click('#gc-ok'); time.sleep(0.3)
            ok('Fatto chiude il pannello e il comando', not pg.is_visible('#gioco-pan') and not pg.evaluate("document.querySelector('[data-asm-tool=\"gioco\"]').classList.contains('on')"))

            # ---- 2. il plexiglass nella scanalatura: 0,5 per lato (le due facce di fianco non si vedono: dal motore)
            o = {x['id']: x for x in api('scene')['objects']}
            rv = pg.evaluate("async ([a, b]) => { const r = await (await fetch('/api/asm_vano', {method: 'POST', body: JSON.stringify([a, b])})).json();"
                             " await window.__steelcad.apply(r); return r.ok; }",
                             [{'inst': 'I2', 'face': o['I2']['faces'][0]['index']}, {'inst': 'I1', 'face': o['I1']['faces'][0]['index']}])
            time.sleep(1.2)
            pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
            pg.evaluate("(() => { for (let i = 0; i < 20; i++) { const e = document.querySelector('#mis-box .dim'); if (!e) break; e.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true})); } })()")
            fp = pg.evaluate(FACCIA, ['I2', [1, 0, 0], None]); fq = pg.evaluate(FACCIA, ['I1', [-1, 0, 0], [916, 460, 10]])
            g = api('asm_gioco', {'inst': 'I2', 'face': fp['index'], 'pt': [915.5, 300, 10]}, {'inst': 'I1', 'face': fq['index']})
            ok(f"scanalatura: {g.get('message')}", g.get('ok') and abs(g['gioco']['facce']['mm'] - 0.5) < 1e-6 and g['gioco']['pezzi']['stato'] == 'dentro')
            pg.evaluate("(r) => window.__gioco.mostra(r)", g); time.sleep(0.6)
            ok('pannello: 0,5 mm tra le facce, i pezzi entrano', '0,5 mm' in pg.inner_text('#gc-facce') and 'Entrano' in pg.inner_text('#gc-pezzi'))
            et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
            ok(f'quote: {et}', 'gioco 0,5' in et and any(e.startswith('entrano') for e in et))
            ok('la quota rossa per «entrano»', pg.evaluate("!!document.querySelector('#mis-box .dim.mis.rosso')"))
            # vicino, sull'angolo dove si misura
            pg.evaluate("""() => { const S = window.__steelcad, T = S.THREE; S.camera.position.set(935, 270, 45); S.controls.target.set(915.75, 300, 10);
              S.camera.zoom = 1; S.camera.updateProjectionMatrix(); S.controls.update(); }""")
            time.sleep(0.6)
            pg.screenshot(path=str(out / f'g2_scanalatura{suf}.png'))
            pg.click('#gc-ok'); time.sleep(0.2)
            pg.evaluate("(() => { for (let i = 0; i < 20; i++) { const e = document.querySelector('#mis-box .dim'); if (!e) break; e.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true})); } })()")
            pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)

            # ---- 3. Quota: i punti della faccia sopra del plexiglass e il suo centro
            comando(pg, '.rbody:not([hidden]) [data-cmd="misura"]'); time.sleep(0.3)
            fs = pg.evaluate(FACCIA, ['I2', [0, 0, 1], None])
            cen = pg.evaluate(NEL_MONDO, ['I2', fs['c']])
            x, y = pg.evaluate(SCHERMO, cen)
            pg.mouse.move(x + 60, y + 40, steps=3); time.sleep(0.3)
            n_off = pg.evaluate("window.__steelcad.mis.offerti?.length || 0")
            ok(f'sulla faccia si vedono i suoi punti ({n_off}: 4 angoli, 4 metà, il centro)', n_off >= 9)
            pg.mouse.move(x + 5, y + 4, steps=3); time.sleep(0.3)
            h = pg.evaluate("(() => { const h = window.__steelcad.mis.hover; return h && { tipo: h.tipo, p: h.p.toArray() }; })()")
            ok(f'vicino al centro si aggancia il centro della faccia: {h}', h and h['tipo'] == 'mezzo' and abs(h['p'][0] - 459) < 0.6 and abs(h['p'][1] - 459) < 0.6)
            ok('il segno dell’aggancio si vede', pg.evaluate("getComputedStyle(document.querySelector('#mis-snap')).display") == 'block'
               and pg.evaluate("document.querySelector('#mis-snap').className") == 'mis-mezzo')
            ok('il cartellino dice «centro della faccia»', 'centro della faccia' in pg.inner_text('#hover-tip'))
            pg.screenshot(path=str(out / f'g3_centro_faccia{suf}.png'))
            pg.mouse.click(x + 5, y + 4); time.sleep(0.3)
            # secondo punto: l'angolo del plexiglass → la quota dal centro
            ang = pg.evaluate(NEL_MONDO, ['I2', [0, 0, 0]])
            api_ang = pg.evaluate("window.__steelcad.mis.cand.filter(c => c.tipo === 'vertice' && Math.abs(c.p.z - 18) < 1e-3).map(c => c.p.toArray())")
            near = min(api_ang, key=lambda q: (q[0] - 2.5) ** 2 + (q[1] - 2.5) ** 2)
            x2, y2 = pg.evaluate(SCHERMO, near)
            pg.mouse.move(x2, y2, steps=3); time.sleep(0.3); pg.mouse.click(x2, y2); time.sleep(0.4)
            et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
            ok(f'quota dal centro all’angolo (913/2·√2 = 645,6): {et}', any(e.startswith('645,5') or e.startswith('645,6') for e in et))
            pg.screenshot(path=str(out / f'g4_quota_dal_centro{suf}.png'))
            pg.keyboard.press('Escape'); time.sleep(0.2)
            if pg.evaluate("!!window.__steelcad.mis"):
                pg.keyboard.press('Escape'); time.sleep(0.2)

            # ---- 4. disegno sulla faccia di una lamiera: il centro della faccia tra gli agganci
            if tema == 'chiaro':
                api('new_project', 'lamiera', {'name': 'L', 'larghezza': 300, 'profondita': 200, 'spessore': 2})
                sid = api('sketch_on_face', 'SM1/sopra')['sketch']
                api('sketch_add_circle', sid, [60, 50], 8)
                pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
                if pg.is_visible('#home-close'):
                    pg.click('#home-close'); time.sleep(0.4)
                pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", sid); time.sleep(1.2)
                c = pg.evaluate("""() => { const v = window.__steelcad.sketch.v, T = window.__steelcad.THREE;
                    const w = new T.Vector3(150, 100, 2); const o = new T.Vector3(...v.origin);
                    return [w.clone().sub(o).dot(new T.Vector3(...v.x_dir)), w.clone().sub(o).dot(new T.Vector3(...v.y_dir))]; }""")
                xs, ys = pg.evaluate("(xy) => { const a = window.__steelcad.skScreen(xy), r = document.querySelector('#c3d').getBoundingClientRect(); return [r.left + a[0], r.top + a[1]]; }", c)
                pg.mouse.move(xs + 4, ys + 3, steps=3); time.sleep(0.4)
                cur = pg.evaluate("(() => { const c = window.__steelcad.sketch.cursor; return c && { how: c.how, xy: c.xy, tipo: c.tipo }; })()")
                ok(f'nel disegno: centro della faccia agganciato {cur}', cur and cur['how'] == 'centro della faccia'
                   and abs(cur['xy'][0] - c[0]) < 1e-6 and abs(cur['xy'][1] - c[1]) < 1e-6)
                ok('il segno dell’aggancio nel disegno', pg.evaluate("getComputedStyle(document.querySelector('#sk-snap')).display") == 'block')
                pg.screenshot(path=str(out / 'g5_disegno_centro.png'))
            if tema == 'scuro':
                ok('tema scuro acceso', pg.evaluate("document.body.classList.contains('dark')"))
                pg.evaluate("window.__steelcad.runCmd('toggle_theme')")          # torna chiaro (si ricorda)
            ok(f'nessun errore nella pagina ({tema})', not err)
            if err:
                print(err)
            pg.close()
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
sys.exit(0 if all(esiti) else 1)
