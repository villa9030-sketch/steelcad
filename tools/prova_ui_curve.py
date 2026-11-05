r"""Prova a schermo di ellissi e curve libere (05/11): sopraluce di un cancello. Nel disegno: mezza ellisse (arco di
ellisse) sopra un rettangolo aperto, dentro una goccia fatta con la curva libera chiusa e un'ellisse intera; si
trascina un punto della curva libera; «Crea piastra»; il pezzo 3D; il DXF di taglio riletto (solo linee e archi) e
disegnato in una foto; il tema scuro.

    <python con playwright> tools\prova_ui_curve.py cartella_screenshot [porta]
"""
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando  # noqa: F401  (comandi della barra, anche nei menu)

ROOT = Path(__file__).resolve().parents[1]
_VENV = ROOT / '.venv' / 'Scripts' / 'python.exe'
PY = Path(os.environ.get('RADIUS_PY') or (_VENV if _VENV.exists() else ROOT.parents[1] / 'steelcad' / '.venv' / 'Scripts' / 'python.exe'))
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5325
CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'


def disegna_dxf(percorso, png):
    """Il DXF riletto, disegnato in una foto (linee nere, archi blu): si vede che è fatto solo di linee e archi."""
    import ezdxf
    from PIL import Image, ImageDraw
    doc = ezdxf.readfile(percorso)
    ent = list(doc.modelspace())
    pts = []
    for e in ent:
        if e.dxftype() == 'LINE':
            pts += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif e.dxftype() in ('ARC', 'CIRCLE'):
            c, r = e.dxf.center, e.dxf.radius
            pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)] if e.dxftype() == 'CIRCLE' else [
                (c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)))
                for a in [e.dxf.start_angle + (e.dxf.end_angle - e.dxf.start_angle) % 360 * k / 8 for k in range(9)]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    W, H, m = 1100, 800, 40
    k = min((W - 2 * m) / (max(xs) - min(xs)), (H - 2 * m) / (max(ys) - min(ys)))
    T = lambda x, y: (m + (x - min(xs)) * k, H - m - (y - min(ys)) * k)  # noqa: E731
    im = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(im)
    conta = {}
    for e in ent:
        t = e.dxftype()
        conta[t] = conta.get(t, 0) + 1
        if t == 'LINE':
            d.line([T(e.dxf.start.x, e.dxf.start.y), T(e.dxf.end.x, e.dxf.end.y)], fill='black', width=2)
        elif t == 'ARC':
            c, r = e.dxf.center, e.dxf.radius
            a0, sw = e.dxf.start_angle, (e.dxf.end_angle - e.dxf.start_angle) % 360
            q = [T(c[0] + r * math.cos(math.radians(a0 + sw * i / 24)), c[1] + r * math.sin(math.radians(a0 + sw * i / 24)))
                 for i in range(25)]
            d.line(q, fill=(31, 94, 255) if conta[t] % 2 else (0, 168, 143), width=3)
            d.ellipse([q[0][0] - 2, q[0][1] - 2, q[0][0] + 2, q[0][1] + 2], fill='red')
    d.text((10, 10), 'DXF riletto: ' + ', '.join(f'{v} {k}' for k, v in sorted(conta.items()))
           + '  (archi alternati blu/verde, puntini rossi = inizio di ogni arco)', fill='black')
    im.save(png)
    return conta


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
            api('new_project', 'zero', {'name': 'Sopraluce'})
            # la base: tre lati di un rettangolo 800 × 300 (sopra va l'arco di ellisse)
            api('sketch_add_polyline', 'S1', [[-400, 0], [-400, -300], [400, -300], [400, 0]], False)
            api('sketch_add_polyline', 'S1', [[-450, 280], [450, 280]], False, True)   # una guida: la vista prende anche l'arco
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', 'S1')
            time.sleep(1.5)
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            def clic(xy, attesa=0.35):
                x, y = a_schermo(xy)
                pg.mouse.move(x - 3, y - 3)
                pg.mouse.move(x, y)
                time.sleep(0.15)
                pg.mouse.click(x, y)
                time.sleep(attesa)

            # ---------------------------------------------------------------- i due comandi nel menu «Forme»
            menu = pg.locator('#ribbon .ralt:has([data-tool="ellipse"]) .ralt-btn')
            if menu.count():
                menu.first.click()
                time.sleep(0.4)
                pg.screenshot(path=str(SHOTS / '00_menu_forme.png'))
                ok('Ellisse e Curva libera nel menu', pg.locator('#ribbon [data-tool="ellipse"]').first.is_visible()
                   and pg.locator('#ribbon [data-tool="spline"]').first.is_visible())
                pg.keyboard.press('Escape')
                time.sleep(0.3)
            # ---------------------------------------------------------------- arco di ellisse sopra la base
            comando(pg, '#ribbon [data-tool="ellipse"]')
            time.sleep(0.3)
            pg.locator('#sk-cmd-extra [data-var="arco"]').click()
            time.sleep(0.2)
            clic([0, 0])                      # il centro: sull'origine
            clic([400, 0])                    # la fine dell'asse grande: sullo spigolo della base
            x, y = a_schermo([0, 240])
            pg.mouse.move(x, y)
            time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '01_ellisse_anteprima.png'))
            ok('anteprima dell’ellisse mentre muovi', pg.evaluate('window.__steelcad.sketch.pts.length') == 2)
            clic([0, 240])
            clic([400, 0])                    # partenza dell'arco: lo spigolo destro
            x, y = a_schermo([-300, 160])
            pg.mouse.move(x, y)
            time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '02_arco_di_ellisse_anteprima.png'))
            clic([-400, 0], 2.0)              # arrivo: lo spigolo sinistro
            v = pg.evaluate('window.__steelcad.sketch.v')
            cu = [c for c in v['curves'] if c['kind'] == 'ellipse']
            ok('arco di ellisse fatto', len(cu) == 1 and not cu[0]['closed'])
            ok('arco attaccato agli spigoli (contorno chiuso)', v['profiles'] == 1)
            print('stato:', v['status'])
            # ---------------------------------------------------------------- una goccia con la curva libera chiusa
            comando(pg, '#ribbon [data-tool="spline"]')
            time.sleep(0.3)
            goccia = [[-250, -60], [-180, -140], [-250, -240], [-320, -140]]
            for q in goccia:
                clic(q)
            x, y = a_schermo([-260, -100])
            pg.mouse.move(x, y)
            time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '03_curva_libera_anteprima.png'))
            clic(goccia[0], 2.0)              # sul primo punto: si chiude
            v = pg.evaluate('window.__steelcad.sketch.v')
            sp = [c for c in v['curves'] if c['kind'] == 'spline']
            ok('curva libera chiusa', len(sp) == 1 and sp[0]['closed'] and len(sp[0]['handles']) == 4)
            # ---------------------------------------------------------------- un'ellisse intera, scritta 200x100
            comando(pg, '#ribbon [data-tool="ellipse"]')
            pg.locator('#sk-cmd-extra [data-var="intera"]').click()
            clic([200, -150])
            pg.keyboard.type('200x100')
            pg.keyboard.press('Enter')
            time.sleep(2.0)
            v = pg.evaluate('window.__steelcad.sketch.v')
            ok('ellisse intera 200×100', any(c['kind'] == 'ellipse' and c['closed'] and abs(c['a'] - 100) < 1e-6
                                             and abs(c['b'] - 50) < 1e-6 for c in v['curves']))
            ok('tre contorni: fuori, goccia, ellisse', v['profiles'] == 1 and not v['sciolte'])
            pg.screenshot(path=str(SHOTS / '04_disegno_fatto.png'))
            # ---------------------------------------------------------------- trascina un punto della goccia
            comando(pg, '#ribbon [data-tool="select"]')
            time.sleep(0.3)
            pid = sp[0]['handles'][1]
            da = next(q['xy'] for q in v['points'] if q['id'] == pid)
            x0, y0 = a_schermo(da)
            x1, y1 = a_schermo([-140, -150])
            pg.mouse.move(x0, y0)
            pg.mouse.down()
            for i in range(1, 9):
                pg.mouse.move(x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * i / 8)
                time.sleep(0.05)
            time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '05_trascina_punto.png'))
            pg.mouse.up()
            time.sleep(2.0)
            v = pg.evaluate('window.__steelcad.sketch.v')
            dopo = next(q['xy'] for q in v['points'] if q['id'] == pid)
            ok(f'il punto trascinato è andato lì ({dopo[0]:.1f}; {dopo[1]:.1f})', math.dist(dopo, [-140, -150]) < 15)
            pg.screenshot(path=str(SHOTS / '06_dopo_trascina.png'))
            pg.evaluate('window.__prova.applyTheme(true)')
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '07_tema_scuro.png'))
            pg.evaluate('window.__prova.applyTheme(false)')
            # ---------------------------------------------------------------- piastra, 3D, DXF
            r = api('create_from_sketch', 'S1', 'plate', {'thickness': 5})
            ok('piastra fatta', r.get('ok'))
            pg.evaluate('window.__steelcad.exitSketch()')
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(2.0)
            pg.screenshot(path=str(SHOTS / '08_pezzo_3d.png'))
            r = api('export', 'dxf')                   # come «DXF di taglio, per il laser…» (file nella cartella di prova)
            print('DXF:', r.get('message'))
            ok('DXF di taglio con i controlli superati', r.get('ok'))
            dxf = r['path']
            conta = disegna_dxf(str(dxf), str(SHOTS / '09_dxf_riletto.png'))
            print('nel DXF:', conta)
            ok('nel DXF solo linee e archi', set(conta) <= {'LINE', 'ARC', 'CIRCLE', 'TEXT'} and conta.get('ARC', 0) > 20)
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
