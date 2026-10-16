r"""Prova dell'interfaccia in un browser invisibile (Chromium headless di Playwright).

Avvia il server di prova con il motore, apre l'app, fa le cose che farebbe una
persona e controlla il risultato. Nessuna finestra sul desktop.

    <python con playwright> tools\prova_ui.py [cartella_screenshot]
"""
import json
import math
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
SHOTS_G = SHOTS


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
            nuovo_subito(pg, ok)
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['telaio', {name: 'Tavolo officina'}])})")
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            time.sleep(0.3)
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
            try:
                cancello(pg, ok, errori)
            except Exception:
                pg.screenshot(path=str(SHOTS / 'errore.png'))
                print('ERRORI CONSOLE', errori, '| PROPS', pg.inner_text('#props')[:300], '| NODI',
                      pg.evaluate('window.__steelcad.nodes.map(n => n.id)'), flush=True)
                raise
            b.close()
    finally:
        srv.kill()
    print(json.dumps({'errori_console': errori, 'screenshot': str(SHOTS)}, ensure_ascii=False))
    return 0 if all(e for _, e in esiti) else 1


def nuovo_subito(pg, ok):
    """Bug 16/10: appena aperta l'app, Nuovo → il pezzo nuovo deve sostituire quello vecchio a video."""
    pg.keyboard.press('Control+N')
    pg.click('.choice button[data-k="piastra"]')
    pg.click('#n-ok')
    pg.wait_for_function("window.__steelcad.state.name === 'Piastra'")
    pg.wait_for_function("window.__steelcad.objs.has('body') && window.__steelcad.objs.size === 1", timeout=8000)
    ok('nuovo progetto subito dopo l’avvio: a video c’è il pezzo nuovo', True)


def da_zero(pg, ok):
    """Lamiera da zero: contorno disegnato col mouse e le lunghezze scritte, foro, poi Crea lamiera."""
    pg.keyboard.press('Escape')
    pg.keyboard.press('Control+N')
    pg.click('.choice button[data-k="zero"]')
    pg.fill('#n-name', 'Staffa')
    pg.click('#n-ok')
    pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.state.name === 'Staffa'")
    time.sleep(0.4)
    box = pg.locator('#c3d').bounding_box()

    def schermo(x, y):
        sx, sy = pg.evaluate('([x, y]) => window.__steelcad.skScreen([x, y])', [x, y])
        return box['x'] + sx, box['y'] + sy

    def muovi(x, y):
        pg.mouse.move(*schermo(x, y), steps=3)

    def clic(x, y):
        muovi(x, y)
        pg.mouse.down()
        pg.mouse.up()

    clic(0, 0)                               # aggancio all'origine
    for (x, y), lung in (((300, 0), '400'), ((400, 150), '200'), ((100, 200), '400')):
        muovi(x, y)
        pg.keyboard.type(lung)
        pg.keyboard.press('Enter')
    clic(0, 0)                               # clic sul primo punto: si chiude
    pg.wait_for_function("window.__steelcad.sketch.v.lines.length === 4 && window.__steelcad.sketch.v.ok")
    stato = pg.evaluate('window.__steelcad.sketch.v.status')
    quote = sorted(pg.locator('.dim').all_inner_texts())
    ok(f'contorno disegnato e chiuso: {stato} {quote}', 'completamente' in stato and quote == ['200', '400'])
    pg.keyboard.press('c')
    clic(100, 100)
    pg.keyboard.type('20')
    pg.keyboard.press('Enter')
    pg.wait_for_function("window.__steelcad.sketch.v.circles.length === 1")
    ok('foro Ø20 scritto: ' + pg.evaluate('window.__steelcad.sketch.v.status'),
       abs(pg.evaluate('window.__steelcad.sketch.v.circles[0].r') - 10) < 1e-9)
    pg.screenshot(path=str(SHOTS_G / '7_sketch.png'))
    pg.click('#sk-make [data-make="sheet"]')
    pg.fill('#m-sp', '2'); pg.fill('#m-r', '2'); pg.fill('#m-k', '0,4')
    pg.click('#m-ok')
    pg.wait_for_function("window.__steelcad.state.sheet && window.__steelcad.state.sheet.data && !window.__steelcad.sketch")
    size = pg.evaluate('window.__steelcad.state.sheet.data.flat_size')
    ok(f'lamiera creata dal disegno: {size}', abs(size[0] - 400) < 1e-6 and abs(size[1] - 200) < 1e-6)
    pg.evaluate("""() => { const o = window.__steelcad.objs.get('body');
        const f = o.data.faces.find(x => x.name && x.name.includes('/lato/')); window.__steelcad.select('body', f.index); }""")
    pg.wait_for_selector('#f-add')
    pg.click('#f-add')
    pg.wait_for_function("window.__steelcad.state.sheet.data.bends.length === 1")
    ok('flangia sul pezzo disegnato', True)
    pg.screenshot(path=str(SHOTS_G / '8_da_zero.png'))
    # riapro lo sketch dall'albero e allungo il pezzo con la quota
    pg.click('#tree .node:has-text("Contorno")')
    pg.wait_for_function("window.__steelcad.sketch")
    pg.locator('.dim', has_text='400').first.click()
    pg.keyboard.press('Control+A'); pg.keyboard.type('500'); pg.keyboard.press('Enter')
    pg.wait_for_function("window.__steelcad.state.sheet.data && Math.round(Math.max(...window.__steelcad.state.sheet.data.flat_size)) >= 500")
    ok('quota 400 → 500 dallo sketch riaperto', True)
    pg.click('#sk-done')
    pg.wait_for_function("!window.__steelcad.sketch")


def scatola(pg, ok):
    """Scatola: 4 flange, angolo chiuso dal pannello, foro disegnato sulla faccia di una flangia."""
    pg.keyboard.press('Escape')
    pg.keyboard.press('Control+N')
    pg.click('.choice button[data-k="lamiera"]')
    pg.fill('#n-name', 'Scatola')
    pg.fill('[data-f="larghezza"]', '400'); pg.fill('[data-f="profondita"]', '300')
    pg.fill('[data-f="raggio"]', '2'); pg.fill('[data-f="k"]', '0,5')
    pg.click('#n-ok')
    pg.wait_for_function("window.__steelcad.state.name === 'Scatola' && window.__steelcad.objs.has('body') && "
                         "window.__steelcad.objs.get('body').data.faces.filter(x => x.name && x.name.includes('/lato/')).length === 4")
    for lato in ('L1', 'L2', 'L3', 'L4'):
        pg.evaluate("""(lato) => { const o = window.__steelcad.objs.get('body');
            const f = o.data.faces.find(x => x.name === 'SM1/lato/' + lato); window.__steelcad.select('body', f.index); }""", lato)
        pg.wait_for_selector('#f-add')
        pg.fill('#f-len', '60')
        pg.click('#f-add')
        pg.wait_for_function("(lato) => window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.some(b => b.edge === lato)", arg=lato)
        pg.wait_for_function("document.querySelector('#props h3')?.innerText.startsWith('Flangia')")
    pg.evaluate("window.__steelcad.select('flange=SM1/FL1')")
    pg.wait_for_selector('.corner[data-other="FL2"] [data-corner]')
    area0 = pg.evaluate('window.__steelcad.state.sheet.data.flat_area')
    pg.select_option('.corner[data-other="FL2"] [data-corner]', 'over')
    pg.wait_for_function("(a) => window.__steelcad.state.sheet.data.flat_area > a + 1", arg=area0)
    diff = pg.evaluate('window.__steelcad.state.sheet.data.flat_area') - area0
    ok(f'angolo chiuso FL1 sopra FL2 dal pannello (+{diff:.1f} mm² di aletta)', abs(diff - 6 * 56) < 1e-6)
    pg.wait_for_function("window.__steelcad.state.scene_version === window.__steelcad.sceneVersion")
    # clic sulla faccia esterna di FL1 → disegna qui → cerchio Ø8 → taglia
    pg.evaluate("""() => { const o = window.__steelcad.objs.get('body');
        const f = o.data.faces.find(x => x.name === 'SM1/FL1/esterno'); window.__steelcad.select('body', f.index); }""")
    pg.wait_for_selector('[data-face-sketch]')
    pg.click('[data-face-sketch]')
    pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_face === 'SM1/FL1/esterno'")
    time.sleep(0.4)
    box = pg.locator('#c3d').bounding_box()
    loc = pg.evaluate("""(P) => { const v = window.__steelcad.sketch.v;
        const d = P.map((c, i) => c - v.origin[i]); const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
        return [dot(d, v.x_dir), dot(d, v.y_dir)]; }""", [200, 0, 30])
    sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', loc)
    pg.keyboard.press('c')
    pg.mouse.move(box['x'] + sx, box['y'] + sy, steps=3)
    pg.mouse.down(); pg.mouse.up()
    pg.keyboard.type('8')
    pg.keyboard.press('Enter')
    pg.wait_for_function("window.__steelcad.sketch.v.circles.length === 1")
    pg.screenshot(path=str(SHOTS_G / '9_su_faccia.png'))
    area1 = pg.evaluate('window.__steelcad.state.sheet.data.flat_area')
    pg.click('#sk-face [data-make="cut"]')
    pg.wait_for_function("(a) => !window.__steelcad.sketch && window.__steelcad.state.sheet.data.flat_area < a - 1", arg=area1)
    diff = area1 - pg.evaluate('window.__steelcad.state.sheet.data.flat_area')
    ok(f'foro Ø8 disegnato sulla faccia della flangia, anche nello sviluppo (−{diff:.2f} mm²)', abs(diff - math.pi * 16) < 0.5)
    pg.evaluate("window.__steelcad.select('body')")
    time.sleep(0.4)
    pg.screenshot(path=str(SHOTS_G / '10_scatola.png'))


def lamiera(pg, ok):
    """Milestone 3 dall'interfaccia: base 500x300 sp. 2, dati di piega, due flange, foro, sviluppo, DXF."""
    pg.keyboard.press('Escape')
    pg.keyboard.press('Control+N')
    pg.click('.choice button[data-k="lamiera"]')
    pg.fill('#n-name', 'Canalina')
    pg.click('#n-ok')
    pg.wait_for_function("window.__steelcad.state.name === 'Canalina' && window.__steelcad.state.sheet")
    pg.click('.tabs button[data-tab="sheet"]')
    ok('scheda Lamiera: mancano raggio e K', 'Mancano' in pg.inner_text('#tab-sheet'))
    pg.fill('#t-radius', '2')
    pg.keyboard.press('Enter')
    pg.wait_for_function("window.__steelcad.state.sheet.def.radius === 2")
    pg.fill('#t-k', '0,4')
    pg.keyboard.press('Enter')
    pg.wait_for_function("window.__steelcad.state.sheet.def.k === 0.4 && !window.__steelcad.state.sheet.missing.length")
    ok('dati di piega inseriti', True)
    for lato in ('L1', 'L3'):
        pg.evaluate("""(lato) => { const o = window.__steelcad.objs.get('body');
            const f = o.data.faces.find(x => x.name === 'SM1/lato/' + lato); window.__steelcad.select('body', f.index); }""", lato)
        pg.wait_for_selector('#f-add')
        pg.fill('#f-len', '30')
        pg.click('#f-add')
        pg.wait_for_function("(lato) => window.__steelcad.state.sheet.data.bends.some(b => b.edge === lato)", arg=lato)
        pg.wait_for_function("document.querySelector('#props h3')?.innerText.startsWith('Flangia')")
    size = pg.evaluate('window.__steelcad.state.sheet.data.flat_size')
    ok(f'U: sviluppo {size}', abs(size[0] - 500) < 1e-6 and abs(size[1] - 352.7964594) < 1e-5)
    pg.fill('#h-u', '100')
    pg.fill('#h-v', '18')
    pg.fill('#h-d', '8')
    pg.click('#h-add')
    pg.wait_for_function("document.querySelectorAll('.holes .h').length === 1")
    ok('foro sulla flangia', True)
    pg.click('.tabs button[data-tab="sheet"]')
    pg.wait_for_selector('#flat-svg')
    time.sleep(0.3)
    pg.screenshot(path=str(SHOTS_G / '6_lamiera.png'))
    pg.click('#tab-sheet [data-cmd="export_dxf"]')
    pg.wait_for_selector('.toast:has-text("Sviluppo salvato")')
    ok('export sviluppo: ' + pg.inner_text('.toast:has-text("Sviluppo salvato")')[:90], True)


def cancello(pg, ok, errori):
    if True:
        if True:
            # cancello da zero: nodo, aste tirate con direzione e lunghezza, chiusura con un clic sul nodo
            pg.keyboard.press('Control+N')
            pg.click('.choice button[data-k="vuoto"]')
            pg.fill('#n-name', 'Cancello')
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.state.name === 'Cancello' && document.querySelectorAll('.node-dot').length === 1")
            pg.click('.node-dot')
            pg.wait_for_selector('#n-len')
            pg.fill('#n-len', '1000'); pg.fill('#n-group', 'Montanti')
            pg.click('[data-dir="Z+"]')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.length === 1 && document.querySelector('#props h3')?.innerText.includes('N1')")
            pg.fill('#n-len', '1500'); pg.fill('#n-group', 'Traversi')
            pg.click('[data-dir="X+"]')
            pg.wait_for_function("document.querySelector('#props h3')?.innerText.includes('N2')")
            pg.fill('#n-len', '1000'); pg.fill('#n-group', 'Montanti')
            pg.click('[data-dir="Z-"]')
            pg.wait_for_function("document.querySelector('#props h3')?.innerText.includes('N3')")
            pg.fill('#n-group', 'Traversi')
            pg.click('#n-link')
            pg.click('.node-dot[data-id="ST1:A"]')
            pg.wait_for_function("window.__steelcad.state.cutlist.pieces === 4 && window.__steelcad.objs.size === 4 && document.querySelector('#props h3')?.innerText.includes('M4')"); time.sleep(0.4)
            righe = pg.evaluate("window.__steelcad.state.cutlist.rows.map(r => [r.length_mm, r.cuts.join('/'), r.qty])")
            ok(f'cancello chiuso 1540/1040 a 45° ({righe})', sorted(righe) == [[1040, '45°/45°', 2], [1540, '45°/45°', 2]])
            pg.screenshot(path=str(SHOTS_G / '4_cancello.png'))
            # giunto a battuta in N1: il traverso passa
            pg.click('.node-dot[data-id="ST1:N1"]')
            pg.wait_for_selector('#n-joint')
            pg.select_option('#n-joint', 'butt')
            pg.check('[data-th="M2"]')
            pg.click('#n-joint-ok')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.some(r => r.cuts.includes('dritto'))")
            ok('giunto a battuta in N1', True)
            pg.screenshot(path=str(SHOTS_G / '5_nodo.png'))
            # elimina un'asta con Canc, poi annulla
            pg.keyboard.press('Escape')
            pg.click('#tree .node:has-text("Traversi") + ul .node >> nth=0')
            pg.wait_for_selector('#p-del')
            pg.keyboard.press('Delete')
            pg.wait_for_function("window.__steelcad.state.cutlist.pieces < 4")
            ok('Canc elimina', True)
            pg.keyboard.press('Control+Z')
            pg.wait_for_function("window.__steelcad.state.cutlist.pieces === 4")
            ok('annulla rimette le aste', True)
            # spostare un nodo sopra un altro: rifiutato con il motivo
            pg.click('.node-dot[data-id="ST1:N1"]')
            pg.wait_for_selector('[data-xyz="2"]')
            pg.fill('[data-xyz="2"]', '0'); pg.click('#n-move')
            pg.wait_for_selector('.toast.err:has-text("Non applicato")')
            ok('nodo sopra un altro: ' + pg.inner_text('.toast.err:has-text("Non applicato")')[:80], pg.evaluate("window.__steelcad.state.cutlist.pieces") == 4)
            lamiera(pg, ok)
            da_zero(pg, ok)
            scatola(pg, ok)
            ok('nessun errore in console', not errori)

if __name__ == '__main__':
    sys.exit(main())
