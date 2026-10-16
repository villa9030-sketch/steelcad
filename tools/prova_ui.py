r"""Prova dell'interfaccia in un browser invisibile (Chromium headless di Playwright).

Avvia il server di prova con il motore, apre l'app, fa le cose che farebbe una
persona e controlla il risultato. Nessuna finestra sul desktop.

    <python con playwright> tools\prova_ui.py [cartella_screenshot]
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = 5079


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000)
    while not srv.stdout.readline().startswith(b"http"):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append((cosa, bool(cond)))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '1_avvio.png'))
            ok('albero con il telaio', 'Telaio superiore' in pg.inner_text('#tree'))
            ok('8 aste nella scena', pg.evaluate('window.__steelcad.objs.size') == 8)
            ok('quote L e P sul modello', pg.locator('.dim').count() == 2)
            ok('cut list 2040', '2.040' in pg.inner_text('#tab-cut') or '2040' in pg.inner_text('#tab-cut'))

            # clic su una gamba nell'albero
            pg.click('#tree .node:has-text("880")')
            pg.wait_for_selector('#p-prof')
            ok('proprietà della gamba', '880 mm' in pg.inner_text('#props'))
            pg.fill('#p-prof', '60x60x3')
            pg.click('#p-apply')
            pg.wait_for_function("document.querySelector('#tab-cut').innerText.includes('60×60×3')")
            ok('profilo cambiato per tutto il gruppo', pg.evaluate(
                "window.__steelcad.state.cutlist.rows.filter(r => r.profile.includes('60')).reduce((a, r) => a + r.qty, 0)") == 4)
            pg.wait_for_function("document.querySelector('#props').innerText.includes('60×60×3')", timeout=5000)
            ok('proprietà aggiornate dopo la modifica', True)
            pg.screenshot(path=str(SHOTS / '2_gambe_60.png'))

            # quota sul modello: L da 2000 a 2400
            pg.locator('.dim', has_text='L').first.click()
            pg.keyboard.press('Control+A')
            pg.keyboard.type('2400')
            pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.state.parameters.find(p => p.name === 'L').value === 2400")
            righe = pg.evaluate('window.__steelcad.state.cutlist.rows.map(r => r.length_mm)')
            ok(f'L=2400 → telaio 2440 ({righe})', 2440 in righe)

            # palette: H = 750
            pg.keyboard.press('Control+K')
            pg.keyboard.type('H = 750')
            pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.state.parameters.find(p => p.name === 'H').value === 750")
            righe = pg.evaluate('window.__steelcad.state.cutlist.rows.map(r => r.length_mm)')
            ok(f'palette H=750 → gambe 730 ({righe})', 730 in righe)

            # annulla
            pg.keyboard.press('Control+Z')
            pg.wait_for_function("window.__steelcad.state.parameters.find(p => p.name === 'H').value === 900")
            ok('annulla riporta H a 900', True)

            # clic nel viewer al centro di una gamba proiettata
            pt = pg.evaluate("""() => { const o = window.__steelcad.objs.get('ST1/G1'); const THREE_box = o.mesh.geometry;
               THREE_box.computeBoundingBox(); const c = THREE_box.boundingBox.getCenter(o.mesh.position.clone());
               c.project(window.__steelcad.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
               return [r.left + (c.x + 1) / 2 * r.width, r.top + (1 - c.y) / 2 * r.height]; }""")
            pg.mouse.move(pt[0], pt[1])
            pg.mouse.down(); pg.mouse.up()
            pg.wait_for_function("document.querySelector('#props').innerText.includes('Gambe')", timeout=5000)
            ok('clic nel 3D seleziona la gamba', True)
            pg.keyboard.press('Escape')

            # parametro sbagliato: messaggio chiaro, niente rottura
            pg.fill('#params input[data-p="P"]', 'P*2')
            pg.keyboard.press('Enter')
            pg.wait_for_selector('.toast.err')
            pg.click('#tree .node.root'); time.sleep(0.4)
            ok('errore chiaro, una volta sola: ' + pg.inner_text('.toast.err')[:90], pg.locator('.toast.err').count() == 1)

            # piastra: nuovo progetto, clic su faccia, export DXF
            pg.keyboard.press('Control+N')
            pg.click('.choice button[data-k="piastra"]')
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.state.name === 'Piastra'")
            time.sleep(0.4)
            ok('piastra: quote 300, 200, Ø30', sorted(pg.locator('.dim').all_inner_texts()) == sorted(['larghezza300', 'altezza200', 'foroØ30']))
            pg.click('.dim:has-text("larghezza")')
            pg.keyboard.press('Control+A'); pg.keyboard.type('400'); pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.state.info.part && Math.round(window.__steelcad.state.info.part.size_mm[0]) === 400")
            ok('larghezza 400 → pezzo 400 largo', True)
            pg.screenshot(path=str(SHOTS / '3_piastra.png'))
            pg.keyboard.press('Control+K'); pg.keyboard.type('dxf'); pg.keyboard.press('Enter')
            pg.wait_for_selector('.toast:has-text("DXF salvato")')
            ok('export DXF: ' + pg.inner_text('.toast:has-text("DXF")'), True)
            pg.keyboard.press('Control+S')
            pg.wait_for_function('window.__steelcad.state.path && !window.__steelcad.state.dirty')
            ok('salvataggio', any(cart.glob('*.steelcad')))
            ok('nessun errore in console', not errori)
            b.close()
    finally:
        srv.kill()
    print(json.dumps({'errori_console': errori, 'screenshot': str(SHOTS)}, ensure_ascii=False))
    return 0 if all(e for _, e in esiti) else 1


if __name__ == '__main__':
    sys.exit(main())
