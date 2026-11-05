r"""Prova delle linee guida pronte e delle quote che cambiano tipo (05/11, idee da SolidCraft), come una persona:

Da zero: una linea storta, due cerchi, uno spigolo. «Linea guida» con i suoi modi nella barretta «Come:»:
orizzontale per il centro del foro, parallela a 15 (scritto), perpendicolare da un punto, a 30° dalla punta,
bisettrice dello spigolo, tangente da un punto al cerchio, tangente comune ai due cerchi. Ogni volta l'anteprima
prima del clic. Poi la linea di partenza si allunga e gira: le guide seguono. Le quote: R del raccordo → Ø → sviluppo
⌒ → di riferimento (tra parentesi) → di nuovo normale. Tema scuro.

    <python con playwright> tools\prova_ui_costruzione.py cartella_screenshot [porta]
"""
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or sys.executable)
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5324
CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'


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
            assert api('new_project', 'zero', {'name': 'Guide'})['ok']
            sid = 'S1'
            assert api('sketch_add_polyline', sid, [[0, 0], [100, 40]], False)['ok']          # la linea storta
            assert api('sketch_add_polyline', sid, [[-60, 0], [-10, 0], [-10, 60]], False)['ok']  # lo spigolo
            assert api('sketch_add_circle', sid, [50, 110], 15)['ok']
            assert api('sketch_add_circle', sid, [140, 120], 10)['ok']
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(0.8)
            if not pg.evaluate('!!window.__steelcad.sketch'):
                pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1.2)
            pg.keyboard.press('F9'); time.sleep(0.2)                  # niente griglia: i punti dove clicco
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            def clic(xy, prima=None):
                x, y = a_schermo(xy)
                if prima:
                    pg.mouse.move(*a_schermo(prima)); time.sleep(0.15)
                pg.mouse.move(x - 3, y); time.sleep(0.1)
                pg.mouse.move(x, y); time.sleep(0.5)
                pg.mouse.click(x, y); time.sleep(0.3)

            def muovi(xy):
                x, y = a_schermo(xy)
                pg.mouse.move(x - 2, y); time.sleep(0.1)
                pg.mouse.move(x, y); time.sleep(0.7)

            def v():
                return pg.evaluate('window.__steelcad.sketch.v')

            def guide():
                # le guide (non gli aiuti dei vincoli: il piede della parallela, il raggio fino alla tangenza)
                return [l for l in v()['lines'] if l.get('construction') and not l.get('ref')
                        and not l['label'].startswith(('piede', 'raggio'))]

            def nuova(prima):
                vecchie = {l['id'] for l in prima}
                return [l for l in guide() if l['id'] not in vecchie]

            def dir_(l):
                (ax, ay), (bx, by) = l['xa'], l['xb']
                L = math.hypot(bx - ax, by - ay)
                return (bx - ax) / L, (by - ay) / L

            def scegli(k):
                pg.locator(f'#sk-cmd-extra [data-var="{k}"]').click(); time.sleep(0.3)

            # il comando: i modi nella barretta «Come:»
            comando(pg, '#ribbon [data-tool="guide"]'); time.sleep(0.4)
            modi = pg.evaluate("[...document.querySelectorAll('#sk-cmd-extra [data-var]')].map(b => b.textContent)")
            ok(f'«Linea guida»: i 7 modi nella barretta ({modi})', len(modi) == 7)
            ok('la barretta dice «Come:»', pg.locator('#sk-cmd-label').text_content() == 'Come:')

            # 1. orizzontale per il centro del foro
            g0 = guide()
            scegli('hv')
            clic([50, 110])
            muovi([110, 112])
            pg.screenshot(path=str(SHOTS / '01_orizzontale_anteprima.png'))
            ok('anteprima: si vede la guida prima del clic', pg.evaluate('!!window.__steelcad.sketch.gdPrev'))
            clic([110, 112]); time.sleep(1.2)
            n = nuova(g0)
            ok(f'guida orizzontale per il centro del foro ({[(l["xa"], l["xb"]) for l in n]})',
               len(n) == 1 and abs(n[0]['xa'][1] - 110) < 1e-6 and abs(n[0]['xb'][1] - 110) < 1e-6)

            # 2. parallela a 15 dalla linea storta (scritto col comando acceso), sopra
            g0 = guide()
            scegli('parallela')
            pg.mouse.move(*a_schermo([30, 60])); time.sleep(0.2)
            pg.keyboard.type('15'); pg.keyboard.press('Enter'); time.sleep(0.3)
            ok(f'la distanza scritta va nella casella ({pg.locator("#sk-var-g").input_value()})', pg.locator('#sk-var-g').input_value() == '15')
            muovi([50, 21])
            pg.screenshot(path=str(SHOTS / '02_parallela_anteprima.png'))
            clic([50, 21]); time.sleep(1.2)
            n = nuova(g0)
            ok('parallela fatta', len(n) == 1)
            if n:
                u = dir_(n[0])
                d = abs((n[0]['xa'][0]) * -0.371390676 + (n[0]['xa'][1]) * 0.928476691)
                ok(f'parallela alla linea, a 15 mm ({u}, {d:.4f})', abs(u[0] * 0.371390676 - u[1] * 0.928476691) < 1e-6 and abs(d - 15) < 1e-4)
            etich = pg.evaluate("[...document.querySelectorAll('#dims .dim')].map(e => e.textContent)")
            ok(f'la quota 15 della distanza si vede ({etich})', '15' in etich)

            # 3. perpendicolare dalla linea per un punto
            g0 = guide()
            scegli('perpendicolare')
            clic([75, 30], prima=[75, 25])
            muovi([85, 10])
            pg.screenshot(path=str(SHOTS / '03_perpendicolare_anteprima.png'))
            clic([85, 10]); time.sleep(1.2)
            n = nuova(g0)
            ok('perpendicolare fatta', len(n) == 1 and abs(sum(a * b for a, b in zip(dir_(n[0]), (0.928476691, 0.371390676)))) < 1e-6)

            # 4. a 30° dalla punta della linea
            g0 = guide()
            scegli('angolo')
            pg.locator('#sk-var-g').fill('30'); pg.locator('#sk-var-g').press('Enter'); time.sleep(0.2)
            clic([60, 24], prima=[60, 30])
            clic([100, 40])
            muovi([140, 80])
            pg.screenshot(path=str(SHOTS / '04_angolo_anteprima.png'))
            clic([140, 80]); time.sleep(1.2)
            n = nuova(g0)
            if n:
                u = dir_(n[0])
                a = math.degrees(math.acos(abs(u[0] * 0.928476691 + u[1] * 0.371390676)))
                ok(f'a 30° dalla linea ({a:.4f}°)', abs(a - 30) < 1e-4)
            else:
                ok('guida ad angolo fatta', False)

            # 5. bisettrice dello spigolo
            g0 = guide()
            scegli('bisettrice')
            clic([-40, 0], prima=[-40, 5])
            clic([-10, 30], prima=[-5, 30])
            muovi([-40, 30])
            pg.screenshot(path=str(SHOTS / '05_bisettrice_anteprima.png'))
            clic([-40, 30]); time.sleep(1.2)
            n = nuova(g0)
            ok('bisettrice a 45° nello spigolo', len(n) == 1 and abs(abs(dir_(n[0])[0]) - abs(dir_(n[0])[1])) < 1e-6)

            # 6. tangente dalla punta della linea al cerchio
            g0 = guide()
            scegli('tangente')
            clic([0, 0])
            muovi([37, 118])
            pg.screenshot(path=str(SHOTS / '06_tangente_anteprima.png'))
            clic([50 - 15 * 0.8, 110 + 15 * 0.6], prima=[30, 130]); time.sleep(1.2)
            n = nuova(g0)
            ok('tangente da un punto fatta', len(n) == 1)

            # 7. tangente comune ai due cerchi, sopra
            g0 = guide()
            scegli('tangente2')
            clic([50, 125], prima=[50, 135])
            clic([140, 130], prima=[140, 140])
            time.sleep(1.2)
            n = nuova(g0)
            ok('tangente comune fatta', len(n) == 1)
            pg.keyboard.press('Escape'); time.sleep(0.3)
            pg.screenshot(path=str(SHOTS / '07_tutte_le_guide.png'))

            # 8. la linea di partenza si allunga: le guide la seguono
            st = api('state')
            lun = next((d for d in st['dimensions'] if d['sketch'] == sid and d['type'] == 'length'
                        and abs((d['value'] or 0) - math.hypot(100, 40)) < 1e-3), None)
            ok('la quota della linea storta c’è', lun is not None)
            if lun:
                r = api('set_dimension', sid, lun['dim'], '150')
                pg.evaluate('(r) => window.__steelcad.apply(r)', r); time.sleep(1.5)
                par = [l for l in guide() if abs(math.hypot(l['xb'][0] - l['xa'][0], l['xb'][1] - l['xa'][1]) - 150) < 1e-4]
                ok(f'la parallela si è allungata con la linea ({len(par)})', len(par) == 1)
                pg.screenshot(path=str(SHOTS / '08_linea_allungata.png'))

            # 9. le quote: R del raccordo → Ø → ⌒ → di riferimento → normale
            r = api('sketch_add_rectangle_rounded', sid, [200, -20], [300, 40], 8)
            assert r['ok']
            pg.evaluate('(r) => window.__steelcad.apply(r)', r)
            time.sleep(1.2)
            pg.evaluate("() => window.__steelcad.runCmd('fit')"); time.sleep(1.2)
            pg.evaluate("() => window.__steelcad.setTool && window.__steelcad.setTool('select')")
            quota = lambda testo: pg.locator('#dims .dim').filter(has_text=testo).first  # noqa: E731
            quota('R8').click(); time.sleep(0.4)
            tipi = pg.evaluate("[...document.querySelectorAll('#dims .dim.edit .dim-tipi button')].map(b => b.textContent)")
            ok(f'accanto al numero: Ø, ⌒, ( ) ({tipi})', tipi == ['Ø', '⌒', '( )'])
            pg.locator('#dims .dim.edit').screenshot(path=str(SHOTS / '09_quota_tipi.png'))
            pg.screenshot(path=str(SHOTS / '09_quota_tipi_intera.png'))
            pg.click('#dims .dim.edit .dim-tipi [data-tipo="diameter"]'); time.sleep(1.2)
            ok('R8 → Ø16 con un clic', quota('Ø16').count() == 1)
            quota('Ø16').click(); time.sleep(0.4)
            pg.click('#dims .dim.edit .dim-tipi [data-tipo="arclength"]'); time.sleep(1.2)
            sv = pg.evaluate("[...document.querySelectorAll('#dims .dim')].map(e => e.textContent).filter(t => t.startsWith('⌒'))")
            ok(f'Ø16 → sviluppo dell’arco ⌒12,566 ({sv})', sv == ['⌒12,566'])
            pg.screenshot(path=str(SHOTS / '10_sviluppo.png'))
            quota('⌒12,566').click(); time.sleep(0.4)
            pg.click('#dims .dim.edit .dim-tipi [data-tipo="rif"]'); time.sleep(1.2)
            ok('di riferimento: tra parentesi', quota('(⌒12,566)').count() == 1)
            quota('(⌒12,566)').click(); time.sleep(0.5)
            ok('clic sulla quota di riferimento: «Falla comandare»', pg.locator('#toasts .ta').filter(has_text='Falla comandare').count() >= 1)
            pg.screenshot(path=str(SHOTS / '11_riferimento.png'))
            pg.locator('#toasts .ta').filter(has_text='Falla comandare').first.click(); time.sleep(1.2)
            ok('torna normale', quota('⌒12,566').count() == 1 and quota('(⌒12,566)').count() == 0)
            # cambio lo sviluppo: il raccordo cambia raggio
            quota('⌒12,566').click(); time.sleep(0.3)
            pg.keyboard.press('Control+A'); pg.keyboard.type('20'); pg.keyboard.press('Enter'); time.sleep(1.5)
            archi = [a['r'] for a in v()['arcs']]
            ok(f'sviluppo 20: i raccordi diventano R{20 / (math.pi / 2):.3f} ({archi})', archi and all(abs(r - 20 / (math.pi / 2)) < 1e-4 for r in archi))
            pg.screenshot(path=str(SHOTS / '12_sviluppo_20.png'))

            # 10. tema scuro: il comando e la quota aperta
            pg.evaluate("document.body.classList.add('dark')"); time.sleep(0.3)
            comando(pg, '#ribbon [data-tool="guide"]'); time.sleep(0.3)
            scegli('parallela')
            muovi([60, 10])
            pg.screenshot(path=str(SHOTS / '13_scuro_parallela.png'))
            pg.keyboard.press('Escape'); time.sleep(0.2)
            quota('⌒20').click(); time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '14_scuro_quota.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    ok('niente errori nella console', not errori)
    print(f'{sum(esiti)}/{len(esiti)} OK')
    sys.exit(0 if all(esiti) else 1)


if __name__ == '__main__':
    main()
