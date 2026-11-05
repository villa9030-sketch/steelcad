r"""Prova a schermo degli strumenti di disegno nuovi (05/11, idee da SolidCraft):
- Serie attorno a un centro: 8 fori su una flangia tonda (l'anteprima mentre scrivi, il centro proposto, il clic sul
  centro), poi l'angolo tra le copie come misura;
- Rettangolo: dal centro, a 3 punti (storto), raccordato (scelti dentro lo strumento);
- Cerchio: per 3 punti, tangente a 2 linee (raggio scritto), tangente a 3 linee.

    <python con playwright> tools\prova_ui_disegno.py cartella_screenshot [porta]
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
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5301
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
            api('new_project', 'lamiera', {'larghezza': 400, 'profondita': 300, 'spessore': 3, 'raggio': 1, 'k': 0.33})
            sid = api('sketch_on_face', 'SM1/sopra')['sketch']
            api('sketch_add_circle', sid, [120, 150], 90)          # la flangia: il giro dei fori
            api('sketch_add_circle', sid, [190, 150], 6)           # il primo foro Ø12
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            time.sleep(1.5)
            box = pg.locator('#c3d').bounding_box()

            def a_schermo(xy):
                x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                return box['x'] + x, box['y'] + y

            def clic(xy, attesa=0.25):
                x, y = a_schermo(xy)
                pg.mouse.move(x - 3, y - 3)
                pg.mouse.move(x, y)
                time.sleep(0.1)
                pg.mouse.click(x, y)
                time.sleep(attesa)

            def muovi(xy):
                x, y = a_schermo(xy)
                pg.mouse.move(x - 2, y - 2)
                pg.mouse.move(x, y)
                time.sleep(0.3)

            def vista():
                return pg.evaluate('window.__steelcad.sketch.v')

            def aspetta(cond, cosa, t=20):
                for _ in range(int(t / 0.25)):
                    if cond():
                        return True
                    time.sleep(0.25)
                print('   (aspettato invano:', cosa, ')')
                return False

            def disegnati(tipo):
                return [x for x in vista()[tipo] if not x.get('ref') and not x.get('construction')]

            # ------------------------------------------------------------------ serie attorno a un centro
            comando(pg, '#ribbon [data-tool="select"]')
            clic([196, 150])
            comando(pg, '#ribbon [data-act="pattern"]')
            pg.wait_for_selector('#p-come', timeout=10000)
            pg.click('#p-come [data-k="giro"]')
            pg.locator('#p-n').fill('8')
            pg.locator('#p-n').dispatch_event('input')
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '01_serie_attorno_anteprima.png'))
            P = pg.evaluate('window.__steelcad.sketch.serieProva')
            ok('anteprima: 8 attorno al centro della flangia, ogni 45°', P and P.get('giro') and P['n'] == 8
               and abs(P['passo'] - 45) < 1e-9 and abs(P['centro'][0] - 120) < 1e-6)
            ok('frase della serie', 'uno ogni 45' in pg.locator('#p-frase').inner_text())
            ok('il centro proposto è quello del cerchio grande', 'Ø180' in pg.locator('#p-centro').inner_text())
            # su metà giro: 5 fori da 0° a 180°
            pg.locator('#p-n').fill('5')
            pg.locator('#p-ang').fill('180')
            pg.locator('#p-ang').dispatch_event('input')
            time.sleep(0.6)
            P = pg.evaluate('window.__steelcad.sketch.serieProva')
            ok('su 180°: uno ogni 45°, il primo e l’ultimo agli estremi', P and abs(P['passo'] - 45) < 1e-9)
            pg.screenshot(path=str(SHOTS / '02_serie_mezzo_giro.png'))
            pg.locator('#p-n').fill('8')
            pg.locator('#p-ang').fill('360')
            pg.locator('#p-ang').dispatch_event('input')
            # il centro col clic sul disegno: il centro del cerchio grande
            clic([120, 150], 0.6)
            ok('clic sul centro: preso il punto (resta attaccato)', 'resta attaccato' in pg.locator('#p-centro').inner_text())
            pg.locator('#m-ok').click()
            ok('8 fori', aspetta(lambda: len([c for c in disegnati('circles') if abs(c['r'] - 6) < 1e-6]) == 8, '8 fori'))
            fori = [c for c in disegnati('circles') if abs(c['r'] - 6) < 1e-6]
            angoli = sorted(round(math.degrees(math.atan2(c['xc'][1] - 150, c['xc'][0] - 120)) % 360, 3) for c in fori)
            ok('fori ogni 45°', angoli == [0, 45, 90, 135, 180, 225, 270, 315])
            par = pg.locator('#params').inner_text()
            ok('l’angolo tra le copie è una misura a sinistra', 'Angolo tra le copie' in par)
            pg.screenshot(path=str(SHOTS / '03_serie_fatta.png'))
            # l'angolo cambiato dopo: i fori girano
            r = api('set_parameter', 'ang1', 30)
            v2 = api('sketch_view', sid)['sketch']
            angoli = sorted(round(math.degrees(math.atan2(c['xc'][1] - 150, c['xc'][0] - 120)) % 360, 3)
                            for c in v2['circles'] if abs(c['r'] - 6) < 1e-6)
            ok('angolo cambiato a 30°: i fori girano', r.get('ok') and angoli == [0, 30, 60, 90, 120, 150, 180, 210])
            api('undo')
            pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
            time.sleep(1.0)

            # ------------------------------------------------------------------ rettangoli
            pg.keyboard.press('Escape')
            comando(pg, '#ribbon [data-tool="rect"]')
            time.sleep(0.3)
            ok('Rettangolo: le scelte di come farlo, sopra la barra', pg.locator('#sk-cmd-extra [data-var="centro"]').is_visible())
            pg.click('#sk-cmd-extra [data-var="centro"]')
            n0 = len(disegnati('lines'))
            clic([320, 230])
            muovi([350, 250])
            pg.screenshot(path=str(SHOTS / '04_rettangolo_dal_centro.png'))
            clic([350, 250], 1.0)
            ok('rettangolo dal centro: 4 lati', aspetta(lambda: len(disegnati('lines')) == n0 + 4, 'rett centro'))
            xs = [x for l in disegnati('lines')[-4:] for x in (l['xa'][0], l['xb'][0])]
            ok('centrato: da 290 a 350', abs(min(xs) - 290) < 1e-6 and abs(max(xs) - 350) < 1e-6)

            pg.click('#sk-cmd-extra [data-var="tre"]')
            n0 = len(disegnati('lines'))
            clic([270, 30])
            a = math.radians(25)
            muovi([270 + 50 * math.cos(a), 30 + 50 * math.sin(a)])     # la direzione del primo lato: storto
            pg.keyboard.type('80')
            pg.keyboard.press('Enter')
            time.sleep(0.3)
            muovi([270 + 80 * math.cos(a) - 30 * math.sin(a), 30 + 80 * math.sin(a) + 30 * math.cos(a)])
            pg.screenshot(path=str(SHOTS / '05_rettangolo_3_punti.png'))
            pg.keyboard.type('30')
            pg.keyboard.press('Enter')
            ok('rettangolo a 3 punti: 4 lati', aspetta(lambda: len(disegnati('lines')) == n0 + 4, 'rett 3p'))
            lati = sorted(round(math.dist(l['xa'], l['xb']), 3) for l in disegnati('lines')[-4:])
            print('   lati:', lati)
            ok('80 × 30, storto', lati == [30, 30, 80, 80])

            pg.click('#sk-cmd-extra [data-var="raccordato"]')
            pg.locator('#sk-var-r').fill('8')
            pg.locator('#sk-var-r').dispatch_event('input')
            n0 = len(vista()['arcs'])
            clic([20, 200])
            muovi([80, 260])
            pg.screenshot(path=str(SHOTS / '06_rettangolo_raccordato.png'))
            pg.keyboard.type('70x50')
            pg.keyboard.press('Enter')
            ok('rettangolo raccordato: 4 raccordi R8', aspetta(lambda: len([x for x in vista()['arcs'] if abs(x['r'] - 8) < 1e-6]) == n0 + 4, 'raccordato'))

            # ------------------------------------------------------------------ cerchi
            comando(pg, '#ribbon [data-tool="circle"]')
            time.sleep(0.3)
            pg.click('#sk-cmd-extra [data-var="tre"]')
            nc = len(disegnati('circles'))
            clic([20, 20])
            clic([60, 20])
            muovi([40, 50])
            pg.screenshot(path=str(SHOTS / '07_cerchio_3_punti.png'))
            clic([40, 50], 1.0)
            ok('cerchio per 3 punti', aspetta(lambda: len(disegnati('circles')) == nc + 1, 'c3p'))

            # tangente a 2 linee: il lato sotto e il lato sinistro del rettangolo dal centro (290..350 × 210..250)
            pg.click('#sk-cmd-extra [data-var="tan2"]')
            nc = len(disegnati('circles'))
            clic([320, 210])
            clic([290, 230])
            muovi([305, 225])
            pg.keyboard.type('8')
            time.sleep(0.4)
            pg.screenshot(path=str(SHOTS / '08_cerchio_tangente_2.png'))
            pg.keyboard.press('Enter')
            ok('cerchio tangente a 2 linee', aspetta(lambda: len(disegnati('circles')) == nc + 1, 'tan2'))
            c = disegnati('circles')[-1]
            ok('tangente: centro a 8 dai due lati', abs(c['xc'][0] - 298) < 1e-3 and abs(c['xc'][1] - 218) < 1e-3 and abs(c['r'] - 8) < 1e-6)

            # tangente a 3 linee: sotto, destro e sopra del rettangolo dal centro → cerchio Ø40 a destra
            pg.click('#sk-cmd-extra [data-var="tan3"]')
            nc = len(disegnati('circles'))
            clic([335, 210])
            clic([350, 230])
            muovi([335, 250])
            pg.screenshot(path=str(SHOTS / '09_cerchio_tangente_3.png'))
            clic([335, 250], 1.0)
            ok('cerchio tangente a 3 linee', aspetta(lambda: len(disegnati('circles')) == nc + 1, 'tan3'))
            c = disegnati('circles')[-1]
            ok('tangente a 3: R20 a destra', abs(c['r'] - 20) < 1e-3 and abs(c['xc'][0] - 330) < 1e-3)
            pg.keyboard.press('Escape')
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '10_tutto.png'))
            st = api('sketch_view', sid)['sketch'].get('status') or {}
            print('stato dello sketch:', st)
            ok('lo sketch è a posto (niente quote doppie o in conflitto)', 'tutto quotato' in str(st) or 'manca' in str(st))
            # tema scuro
            pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
            time.sleep(0.5)
            ok('tema scuro', pg.evaluate("document.body.classList.contains('dark')"))
            comando(pg, '#ribbon [data-tool="rect"]')
            pg.click('#sk-cmd-extra [data-var="raccordato"]')
            clic([130, 20])
            muovi([220, 70])
            pg.screenshot(path=str(SHOTS / '11_scuro_raccordato.png'))
            pg.keyboard.press('Escape')
            pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
