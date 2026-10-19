r"""Prova delle strutture dall'interfaccia, come una persona: pagina iniziale → Scaffale, Cancello, e una
struttura disegnata col mouse (spalla di fronte, ripetuta dietro e collegata), poi il profilo di un'asta.

    <python con playwright> tools\prova_ui_strutture.py cartella_screenshot
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
SHOTS = Path(sys.argv[1])
PORTA = 5097


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                           env=dict(os.environ, STEELCAD_RULES=str(cart / 'regole.json')))
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)

            def home():
                if pg.locator('#home').is_hidden():
                    pg.click('#top .brand')
                pg.wait_for_selector('#home:not([hidden])')

            def pezzi():
                return pg.evaluate('window.__steelcad.state.cutlist.pieces')

            def scena_pronta():
                pg.wait_for_function('window.__steelcad.state.scene_version === window.__steelcad.sceneVersion')
                time.sleep(0.4)

            # 1. scaffale dalla pagina iniziale
            home()
            pg.click('[data-new="scaffale"]')
            pg.fill('[data-f="H"]', '2000')
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.state.name === 'Scaffale' && window.__steelcad.state.cutlist.pieces === 20")
            scena_pronta()
            righe = pg.evaluate("window.__steelcad.state.cutlist.rows.map(r => [r.profile, r.length_mm, r.qty])")
            ok(f'scaffale H 2000: {righe}', ['30×30×2', 1960, 4] in righe)
            pg.screenshot(path=str(SHOTS / 'st1_scaffale.png'))
            pg.wait_for_selector('#tpl-apply')        # appena creato: la scheda con i dati del modello
            ok('scheda del modello aperta a destra', pg.locator('[data-tf="ripiani"]').input_value() == '4')
            pg.fill('[data-tf="ripiani"]', '5')
            pg.click('#tpl-apply')
            pg.wait_for_function("window.__steelcad.state.cutlist.pieces === 24")
            scena_pronta()
            ok('ripiani 4 → 5 dalla scheda: 24 pezzi', True)
            pg.screenshot(path=str(SHOTS / 'st1b_scheda.png'))
            pg.keyboard.press('Control+K'); pg.keyboard.type('L = 1500'); pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.some(r => r.length_mm === 1470)")
            ok('L = 1500 dalla palette: traversi 1470', True)

            # 2. cancello
            home()
            pg.click('[data-new="cancello"]')
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.state.name === 'Cancello' && window.__steelcad.state.cutlist.pieces === 15")
            scena_pronta()
            pg.screenshot(path=str(SHOTS / 'st2_cancello.png'))
            ok('cancello: 11 sbarre + telaio', True)

            # 3. struttura da disegno: rettangolo di fronte, traverso a metà, ripetuta dietro e collegata
            home()
            pg.click('[data-new="disegno"]')
            pg.select_option('[data-f="piano"]', 'XZ')
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.state.name === 'Struttura'")
            time.sleep(0.5)
            box = pg.locator('#c3d').bounding_box()

            def clic(x, y):
                sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [x, y])
                pg.mouse.move(box['x'] + sx, box['y'] + sy, steps=3)
                pg.mouse.down(); pg.mouse.up()

            pg.keyboard.press('r')
            clic(0, 0); clic(400, 300)
            pg.wait_for_function("window.__steelcad.sketch.v.lines.length === 4")
            time.sleep(0.6)                       # il primo disegno si inquadra da solo
            pg.click('#sk-make [data-make="structure"]')
            pg.fill('#st-p', '40x40x3'); pg.fill('#st-n', '2'); pg.fill('#st-d', '500')
            pg.click('#m-ok')
            pg.wait_for_function("!window.__steelcad.sketch && window.__steelcad.state.cutlist.pieces === 12")
            scena_pronta()
            ok(f'struttura disegnata: 2 telai collegati, {pezzi()} pezzi', pezzi() == 12)
            pg.screenshot(path=str(SHOTS / 'st3_disegno.png'))

            # 4. un'asta: profilo diverso solo per lei (eccezione che resta)
            asta = pg.evaluate("[...window.__steelcad.objs.keys()].find(k => k.includes('/K1.1.'))")
            pg.evaluate("(id) => window.__steelcad.select(id)", asta)
            pg.wait_for_selector('#p-prof')
            if pg.locator('#p-all').count():
                pg.uncheck('#p-all')
            pg.fill('#p-prof', '60x60x3')
            pg.click('#p-apply')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.some(r => r.profile.startsWith('60'))")
            ok('profilo cambiato a una sola asta dello scheletro', True)
            ok('nessun errore in console', not errori)
            b.close()
    finally:
        srv.kill()
    print({'errori_console': errori})
    return 0 if all(esiti) else 1


if __name__ == '__main__':
    sys.exit(main())
