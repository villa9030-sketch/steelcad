r"""Prova a schermo di Scala, Spezza e «Salva in DXF» nel disegno (05/11, idee da SolidCraft).

Il caso vero: il DXF del cliente arriva in scala sbagliata. Una staffa 250 × 80 con un foro Ø20: tutto selezionato,
Scala dall'origine «da una misura» (la base adesso è 250, deve essere 1000): l'anteprima tratteggiata mentre si
scrive, poi 1000 × 320. Una linea legata al resto non si scala da sola: la finestra dice perché e non lascia fare.
Spezza la base a 300 (due colori, «300 + 700»), poi il foro in due mezzi archi. «Salva in DXF» dalla barra e dal
tasto destro sull'albero. In fondo la finestra della Scala nel tema scuro.

    <python con playwright> tools\prova_ui_scala_spezza.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5302
CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'


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
            api('new_project', 'zero', {'name': 'Staffa cliente'})
            api('sketch_add_rectangle', 'S1', 'O', [250, 80])
            api('sketch_add_circle', 'S1', [60, 40], 10)

            def entra():
                pg.reload()
                pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
                pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
                pg.evaluate('(s) => window.__steelcad.enterSketch(s)', 'S1')
                time.sleep(1.5)
            entra()
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            v = lambda: pg.evaluate('window.__steelcad.sketch.v')  # noqa: E731

            # ---------------------------------------------------------------- Scala da una misura
            comando(pg, '#ribbon [data-tool="select"]')
            pg.mouse.move(*a_schermo([125, 40]))
            pg.keyboard.press('Control+A')
            time.sleep(0.3)
            comando(pg, '#ribbon [data-act="scale"]')
            time.sleep(0.4)
            ok('barra: «Scala: clic sul punto che resta fermo»', 'resta fermo' in pg.locator('#sk-help').inner_text())
            pg.mouse.move(*a_schermo([0.5, 0.5]))
            time.sleep(0.3)
            pg.mouse.click(*a_schermo([0, 0]))
            pg.wait_for_selector('#sc-modo', timeout=10000)
            pg.locator('#sc-modo [data-k="misura"]').click()
            time.sleep(0.3)
            ok('«adesso è» preso dalla linea più lunga (250)', pg.locator('#sc-a').input_value() == '250')
            pg.locator('#sc-b').fill('1000')
            pg.locator('#sc-b').dispatch_event('input')
            time.sleep(1.0)
            frase = pg.locator('#sc-frase').inner_text()
            print('frase:', frase)
            ok('frase «× 4: 250 × 80 → 1.000 × 320 mm»', '× 4' in frase and '320' in frase)
            ok('anteprima in prova', pg.evaluate('window.__steelcad.sketch.scalaProva.f') == 4)
            ok('barra: «scrivi di quanto nella finestra»', 'finestra' in pg.locator('#sk-help').inner_text())
            # la vista indietro, per vedere tutta l'anteprima (4 volte più grande)
            pg.mouse.move(box['x'] + 300, box['y'] + 500)
            for _ in range(6):
                pg.mouse.wheel(0, 300)
                time.sleep(0.1)
            time.sleep(0.6)
            pg.screenshot(path=str(SHOTS / '01_scala_da_misura_anteprima.png'))
            pg.locator('#m-ok').click()
            time.sleep(2.0)
            xs = [q for l in v()['lines'] if not l['construction'] for q in (l['xa'][0], l['xb'][0])]
            ys = [q for l in v()['lines'] if not l['construction'] for q in (l['xa'][1], l['xb'][1])]
            ok('dopo: 1000 × 320', round(max(xs) - min(xs), 4) == 1000 and round(max(ys) - min(ys), 4) == 320)
            c = [x for x in v()['circles'] if not x['ref']][0]
            ok('foro Ø80 in 240;160', abs(c['r'] - 40) < 1e-6 and abs(c['xc'][0] - 240) < 1e-6 and abs(c['xc'][1] - 160) < 1e-6)
            pg.screenshot(path=str(SHOTS / '02_scalato_1000x320.png'))

            # ---------------------------------------------------------------- Scala che non si può
            linea = api('sketch_add_polyline', 'S1', [{'on': next(l['id'] for l in v()['lines'] if abs(l['xa'][1]) < 1e-6 and abs(l['xb'][1]) < 1e-6), 'xy': [600, 0]}, [600, 120]], False)
            ok('linea attaccata alla base', linea.get('ok'))
            entra()
            nuova = max((l for l in v()['lines'] if abs(l['xa'][0] - 600) < 1e-6 and abs(l['xb'][0] - 600) < 1e-6), key=lambda l: l['id'])
            comando(pg, '#ribbon [data-tool="select"]')
            pg.mouse.click(*a_schermo([600, 60]))
            time.sleep(0.4)
            comando(pg, '#ribbon [data-act="scale"]')
            time.sleep(0.3)
            pg.mouse.move(*a_schermo([600.5, 120.5]))
            time.sleep(0.3)
            pg.mouse.click(*a_schermo([600, 120]))
            pg.wait_for_selector('#sc-modo', timeout=10000)
            pg.locator('#sc-modo [data-k="fattore"]').click()
            pg.locator('#sc-fatt').fill('2')
            pg.locator('#sc-fatt').dispatch_event('input')
            pg.wait_for_function("document.getElementById('sc-frase')?.classList.contains('no')", timeout=20000)
            frase = pg.locator('#sc-frase').inner_text()
            print('perché no:', frase)
            ok('dice perché non si può e il pulsante è spento', 'Non si può scalare' in frase and pg.locator('#m-ok').is_disabled())
            pg.screenshot(path=str(SHOTS / '03_scala_non_si_puo.png'))
            pg.locator('#m-no').click()
            time.sleep(0.5)
            ok('la linea è rimasta com’era', any(l['id'] == nuova['id'] and abs(l['xb'][1] - 120) < 1e-6 for l in v()['lines']))

            # ---------------------------------------------------------------- Spezza
            pg.evaluate("document.querySelector('#ribbon [data-tool=\"break\"]').closest('.rmenu')?.classList.add('open')")
            time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '03b_menu_modifica.png'))
            pg.evaluate("document.querySelectorAll('.menu-item.open').forEach(x => x.classList.remove('open'))")
            n0 = len(v()['lines'])
            comando(pg, '#ribbon [data-tool="break"]')
            pg.mouse.move(*a_schermo([299, 2]))
            time.sleep(0.3)
            pg.mouse.move(*a_schermo([300, 1]))
            pg.wait_for_function("window.__steelcad.sketch.cutPrev && window.__steelcad.sketch.cutPrev.tool === 'break'", timeout=20000)
            time.sleep(0.4)
            aiuto = pg.locator('#sk-help').inner_text()
            print('aiuto spezza:', aiuto.replace(chr(10), ' '))
            ok('anteprima «300 + 300» (fino alla linea di prima)', '300' in aiuto)
            pg.screenshot(path=str(SHOTS / '04_spezza_anteprima.png'))
            pg.mouse.click(*a_schermo([300, 1]))
            time.sleep(1.5)
            ok('una linea in più, niente cancellato', len(v()['lines']) == n0 + 1)
            # il cerchio: due mezzi archi
            pg.mouse.move(*a_schermo([279, 161]))
            time.sleep(0.3)
            pg.mouse.move(*a_schermo([280, 160]))
            pg.wait_for_function("window.__steelcad.sketch.cutPrev && window.__steelcad.sketch.cutPrev.kind === 'circle'", timeout=20000)
            time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '05_spezza_cerchio.png'))
            pg.mouse.click(*a_schermo([280, 160]))
            time.sleep(1.5)
            ok('il foro è due mezzi archi', len([x for x in v()['circles'] if not x['ref']]) == 0 and len(v()['arcs']) == 2)

            # ---------------------------------------------------------------- Salva in DXF
            pg.keyboard.press('Escape')
            time.sleep(0.3)
            comando(pg, '#ribbon #sk-dxf')
            pg.wait_for_selector('#fatto-apri', timeout=20000)
            time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '06_dxf_salvato.png'))
            testo = pg.locator('#modal-box').inner_text()
            print('dxf:', testo.replace(chr(10), ' / '))
            f = list(cart.glob('*.dxf'))
            ok('file DXF nella cartella', len(f) == 1)
            if f:
                import ezdxf
                tipi = sorted(e.dxftype() for e in ezdxf.readfile(f[0]).modelspace())
                print('nel DXF:', tipi)
                ok('archi veri e linee nel DXF', tipi.count('ARC') == 2 and tipi.count('LINE') == 6)
                f[0].unlink()
            pg.locator('#m-ok').click()
            time.sleep(0.3)
            # dal tasto destro sull'albero, fuori dal disegno
            pg.locator('#sk-done').first.click()
            time.sleep(1.5)
            nodo = pg.locator('#tree .node[data-ref="S1"]').first
            nodo.click(button='right')
            pg.wait_for_selector('#menu-albero [data-v="dxf"]', timeout=10000)
            pg.screenshot(path=str(SHOTS / '07_albero_salva_dxf.png'))
            pg.locator('#menu-albero [data-v="dxf"]').click()
            pg.wait_for_selector('#fatto-apri', timeout=20000)
            ok('DXF anche dal tasto destro', len(list(cart.glob('*.dxf'))) == 1)
            pg.locator('#m-ok').click()

            # ---------------------------------------------------------------- tema scuro
            if not pg.evaluate("document.body.classList.contains('dark')"):
                pg.click('#navbar [data-cmd="toggle_theme"]')
            time.sleep(0.3)
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', 'S1')
            time.sleep(1.5)
            ok('tema scuro', pg.evaluate("document.body.classList.contains('dark')"))
            comando(pg, '#ribbon [data-tool="select"]')
            pg.mouse.move(*a_schermo([500, 160]))
            pg.keyboard.press('Control+A')
            comando(pg, '#ribbon [data-act="scale"]')
            time.sleep(0.3)
            pg.mouse.move(*a_schermo([0.5, 0.5]))
            time.sleep(0.3)
            pg.mouse.click(*a_schermo([0, 0]))
            pg.wait_for_selector('#sc-modo', timeout=10000)
            pg.locator('#sc-modo [data-k="fattore"]').click()
            pg.locator('#sc-fatt').fill('0,5')
            pg.locator('#sc-fatt').dispatch_event('input')
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '08_scala_tema_scuro.png'))
            pg.locator('#m-no').click()
            comando(pg, '#ribbon [data-tool="break"]')
            pg.mouse.move(*a_schermo([799, 321]))
            time.sleep(0.3)
            pg.mouse.move(*a_schermo([800, 320]))
            pg.wait_for_function("window.__steelcad.sketch.cutPrev && window.__steelcad.sketch.cutPrev.tool === 'break'", timeout=20000)
            time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '09_spezza_tema_scuro.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
