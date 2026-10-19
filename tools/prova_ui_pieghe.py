r"""Prova dell'interfaccia per le pieghe: flange sulla punta (scatola bordata), faccia di lavoro,
"Spiega" e disegno sullo sviluppo. Come tools/prova_ui.py, in un browser invisibile.

    <python con playwright> tools\prova_ui_pieghe.py cartella_screenshot [--chrome]

--chrome usa il Chrome installato invece del Chromium di Playwright.
"""
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
SHOTS = Path(sys.argv[1])
PORTA = 5093


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    import os
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                           env=dict(os.environ, STEELCAD_RULES=str(cart / 'regole_lamiera.json')))   # le regole di prova non vanno nei Documenti
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    def faccia(pg, nome):
        pg.evaluate("""(n) => { const o = window.__steelcad.objs.get('body');
            const f = o.data.faces.find(x => x.name === n); window.__steelcad.select('body', f.index); }""", nome)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel='chrome' if '--chrome' in sys.argv else None, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['lamiera', "
                        "{name: 'Scatola', larghezza: 400, profondita: 300, spessore: 2, raggio: 2, k: 0.5}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.objs.has('body')")
            for lato in ('L1', 'L2', 'L3', 'L4'):
                faccia(pg, 'SM1/lato/' + lato)
                pg.wait_for_selector('#f-add')
                pg.fill('#f-len', '60')
                pg.click('#f-add')
                if lato == 'L1':
                    # chi clicca svelto: subito un altro lato, mentre la flangia si sta ancora costruendo
                    faccia(pg, 'SM1/lato/L2')
                    pg.wait_for_function("window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.some(b => b.edge === 'L1')")
                    time.sleep(1.2)
                    ok(f'clic svelto su un altro lato: il pannello resta su quel lato ({pg.inner_text("#f-add")!r})',
                       pg.locator('#f-add').count() == 1 and 'destro' in pg.inner_text('#f-add'))
                    continue
                pg.wait_for_function("(l) => window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.some(b => b.edge === l)", arg=lato)
                pg.wait_for_function("document.querySelector('#props h3')?.innerText.startsWith('Flangia')")
            # 0) il bordo si accende passandoci sopra: punta di FL1 (lunga 400) → flangia lì, nient'altro
            pg.wait_for_function("window.__steelcad.state.scene_version === window.__steelcad.sceneVersion")
            pg.keyboard.press('0'); time.sleep(0.5)
            e = pg.evaluate("window.__steelcad.bendEdges.find(e => e.id === 'tip:FL1')")
            box = pg.locator('#c3d').bounding_box()
            sx, sy = pg.evaluate("(p) => { const v = new window.__steelcad.THREE.Vector3(...p).project(window.__steelcad.camera); const c = document.querySelector('#c3d').getBoundingClientRect(); return [(v.x + 1) / 2 * c.width, (1 - v.y) / 2 * c.height]; }",
                                 [(e['a'][i] + e['b'][i]) / 2 for i in range(3)])
            pg.mouse.move(box['x'] + sx, box['y'] + sy)
            time.sleep(0.3)
            ok(f'bordo acceso col mouse: {pg.inner_text("#hover-tip")!r}', 'punta di FL1' in pg.inner_text('#hover-tip'))
            pg.mouse.click(box['x'] + sx, box['y'] + sy)
            pg.wait_for_function("document.querySelector('#props h3')?.innerText === 'Flangia su questo bordo'")
            ok('pannello del solo bordo cliccato', 'punta di FL1' in pg.inner_text('#props'))
            pg.screenshot(path=str(SHOTS / '0b_bordo.png'))
            pg.keyboard.press('Escape')
            # 1) piega sulla punta: dal pannello della flangia
            pg.wait_for_function("window.__steelcad.state.scene_version === window.__steelcad.sceneVersion")
            pg.evaluate("window.__steelcad.select('flange=SM1/FL1')")
            pg.wait_for_selector('#f-punta summary')
            pg.click('#f-punta summary')                           # la sezione si apre col clic
            pg.wait_for_selector('#t-add')
            ok('pannello flangia: sezione "Piega sulla punta"', 'piega sulla punta' in pg.inner_text('#props').lower())
            pg.fill('#t-len', '20')
            pg.click('#t-add')
            pg.wait_for_function("window.__steelcad.state.sheet.data.bends.some(b => b.parent === 'FL1')")
            ok('flangia FL5 sulla punta di FL1', True)
            pg.wait_for_function("document.querySelector('#props h3')?.innerText === 'Flangia FL5'")
            ok('selezionata la nuova flangia', 'sulla punta di FL1' in pg.inner_text('#props'))
            # ... e cliccando la punta di FL2
            for madre in ('FL2', 'FL3', 'FL4'):
                faccia(pg, f'SM1/{madre}/punta')          # subito, senza aspettare che il pezzo sia ricostruito
                pg.wait_for_function("(m) => document.querySelector('#props h3')?.innerText === 'Flangia ' + m && document.querySelector('#t-add')", arg=madre)
                if not pg.is_visible('#t-len'):
                    pg.click('#f-punta summary')
                pg.fill('#t-len', '20')
                pg.click('#t-add')
                try:
                    pg.wait_for_function("(m) => window.__steelcad.state.sheet.data.bends.some(b => b.parent === m)", arg=madre, timeout=8000)
                except Exception:
                    print('   bloccato su', madre, '| toast:', pg.inner_text('#toasts'), '| props:', pg.inner_text('#props')[:200])
                    raise
                if madre == 'FL2':
                    # primo angolo tra due bordi: chiede come chiuderlo
                    pg.wait_for_selector('#modal:not([hidden]) .choice button[data-k="miter"]')
                    ok('al primo angolo tra i bordi chiede: lati lunghi, lati corti o 45°',
                       pg.locator('#modal .choice button').count() == 3)
                    pg.screenshot(path=str(SHOTS / '0_domanda_angoli.png'))
                    pg.click('#modal .choice button[data-k="miter"]')
                    pg.wait_for_function("window.__steelcad.state.sheet.data.tip_mode === 'miter'")
            st = pg.evaluate('window.__steelcad.state')
            ok(f'scatola bordata: 8 pieghe, nessun errore ({len(st["sheet"]["data"]["bends"])}, {len(st["errors"])})',
               len(st['sheet']['data']['bends']) == 8 and not st['errors'])
            ok('albero in parole: "sulla piega davanti"', 'sulla piega davanti' in pg.inner_text('#tree'))
            madri = sorted(b['parent'] for b in st['sheet']['data']['bends'] if b['parent'])
            ok(f'ogni bordo sulla parete cliccata ({madri})', madri == ['FL1', 'FL2', 'FL3', 'FL4'])
            ok('nessuna altra domanda dopo la scelta', pg.locator('#modal:not([hidden])').count() == 0)
            pg.evaluate("window.__steelcad.select('flange=SM1/FL6')")
            pg.wait_for_selector('#f-tipc')
            pg.select_option('#f-tipc', 'long')
            pg.wait_for_function("window.__steelcad.state.sheet.data.tip_mode === 'long'")
            w = pg.evaluate("Object.fromEntries(window.__steelcad.state.sheet.data.bends.map(b => [b.flange, b.width]))")
            ok(f'dal pannello: dritti, lati lunghi interi (FL5 {w["FL5"]:.0f}, FL6 {w["FL6"]:.1f})',
               abs(w['FL5'] - 392) < 1e-6 and w['FL6'] < 262)
            pg.wait_for_function("document.querySelector('#f-tipc')?.value === 'long'")
            time.sleep(0.6)                  # il pannello si ridisegna dopo la modifica
            pg.select_option('#f-tipc', 'miter')
            pg.wait_for_function("window.__steelcad.state.sheet.data.tip_mode === 'miter'")
            pg.keyboard.press('Escape')
            pg.keyboard.press('0')
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '1_scatola_bordata.png'))

            # 2) disegna su una faccia: si vede solo la faccia
            pg.wait_for_function("window.__steelcad.state.scene_version === window.__steelcad.sceneVersion")
            faccia(pg, 'SM1/FL1/esterno')
            pg.wait_for_selector('[data-face-sketch]')
            pg.click('[data-face-sketch]')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_face === 'SM1/FL1/esterno'")
            time.sleep(0.5)
            look = pg.evaluate('window.__steelcad.look')
            ok(f'sulla faccia: pezzo nascosto, faccia piena {look}', not look['model'] and look['work'])
            pg.screenshot(path=str(SHOTS / '2_faccia_di_lavoro.png'))
            pg.keyboard.press('g')
            time.sleep(0.3)
            ok('G mostra il pezzo in trasparenza', pg.evaluate('window.__steelcad.look.model'))
            pg.screenshot(path=str(SHOTS / '3_faccia_con_pezzo.png'))
            pg.keyboard.press('Escape')
            pg.wait_for_function('!window.__steelcad.sketch')
            ok('fuori dallo sketch il pezzo torna', pg.evaluate('window.__steelcad.look.model'))
            pg.wait_for_function("!document.querySelector('#tree').innerText.includes('Sketch: la faccia')", timeout=5000)
            ok('lo sketch lasciato vuoto sparisce dall’albero', True)
            faccia(pg, 'SM1/FL3/esterno')
            pg.wait_for_selector('[data-face-sketch]')
            pg.click('[data-face-sketch]')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_face === 'SM1/FL3/esterno'")
            time.sleep(0.5)
            bordi = pg.evaluate("window.__steelcad.sketch.v.lines.filter(l => l.label === 'bordo del pezzo')")
            ok(f'sulla faccia ci sono i bordi del pezzo ({len(bordi)})', len(bordi) >= 4)
            box = pg.locator('#c3d').bounding_box()
            # offset del contorno intero: prima lo selezioni (doppio clic su un bordo), poi O, 10 + Invio, clic dentro
            l0 = bordi[0]
            pg.keyboard.press('s')
            sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [(l0['xa'][0] + l0['xb'][0]) / 2, (l0['xa'][1] + l0['xb'][1]) / 2])
            pg.mouse.dblclick(box['x'] + sx, box['y'] + sy)
            pg.wait_for_function('window.__steelcad.sketch.sel.size >= 4')
            pg.keyboard.press('o')
            ok('offset: la casella della distanza si vede ed è pronta',
               pg.evaluate("!document.querySelector('#sk-cmd').hidden && document.activeElement.id === 'sk-cmd-in'"))
            pg.keyboard.type('10'); pg.keyboard.press('Enter')
            cx = sum(b['xa'][0] for b in bordi) / len(bordi); cy = sum(b['xa'][1] for b in bordi) / len(bordi)
            sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [cx, cy])
            pg.mouse.move(box['x'] + sx, box['y'] + sy)
            time.sleep(0.4)
            ok('offset: l’anteprima segue il mouse', pg.evaluate('!!window.__steelcad.sketch.pick.prev'))
            pg.mouse.click(box['x'] + sx, box['y'] + sy)
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 4")
            ok('offset 10 dal bordo del pezzo: contorno vero', True)
            pg.keyboard.press('Escape')                  # fine dell'offset
            pg.screenshot(path=str(SHOTS / '3b_offset_dal_bordo.png'))
            v0 = pg.evaluate('window.__steelcad.state.info.part.volume_mm3')
            pg.click('[data-make="cut"]')
            pg.wait_for_function('!window.__steelcad.sketch', timeout=15000)
            st = pg.evaluate('window.__steelcad.state')
            ok(f'finestra tagliata nella parete FL3 ({v0 - st["info"]["part"]["volume_mm3"]:.0f} mm³)',
               not st['errors'] and v0 - st['info']['part']['volume_mm3'] > 1000)

            # 3) spiega
            pg.click('#navbar [data-cmd="unfold"]')
            time.sleep(0.5)
            look = pg.evaluate('window.__steelcad.look')
            ok(f'spiega: sviluppo a video {look}', look['flat'] and not look['model'])
            pg.screenshot(path=str(SHOTS / '4_spiega.png'))
            pg.click('#flat-bar [data-cmd="flat_sketch"]')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_flat === 'SM1'")
            time.sleep(0.5)
            ok('sketch sullo sviluppo: sviluppo a video', pg.evaluate('window.__steelcad.look.flat'))
            # un cerchio Ø20 al centro della base, cliccando come una persona
            box = pg.locator('#c3d').bounding_box()
            pg.keyboard.press('c')
            sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [200, 150])
            pg.mouse.move(box['x'] + sx, box['y'] + sy)
            pg.mouse.click(box['x'] + sx, box['y'] + sy)
            pg.mouse.move(box['x'] + sx + 30, box['y'] + sy)
            pg.keyboard.type('20')
            pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.circles.length === 1')
            # un triangolo con le misure scritte: 40<0, 40<120, poi clic sul primo punto
            pg.keyboard.press('l')
            p0 = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [100, 100])
            pg.mouse.move(box['x'] + p0[0], box['y'] + p0[1])
            pg.mouse.click(box['x'] + p0[0], box['y'] + p0[1])
            for testo in ('40<0', '40<120'):
                pg.keyboard.type(testo)
                pg.keyboard.press('Enter')
            p0 = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [100, 100])
            pg.mouse.move(box['x'] + p0[0], box['y'] + p0[1])
            pg.mouse.click(box['x'] + p0[0], box['y'] + p0[1])
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction && l.label !== 'bordo del pezzo').length === 3")
            angoli = pg.evaluate("""window.__steelcad.sketch.v.lines.filter(l => !l.construction).map(l =>
                Math.round(Math.atan2(l.xb[1] - l.xa[1], l.xb[0] - l.xa[0]) * 1800 / Math.PI) / 10)""")
            ok(f'linee con l’angolo scritto: {angoli}', 0 in angoli and 120 in angoli)
            # e un rettangolo su un bordo (FL5, sulla punta di FL1): a metà del suo tratto dritto nello sviluppo
            d = pg.evaluate('window.__steelcad.state.sheet.data')
            ys = [v for o in d['outline'] for v in o[1::2]]
            y_bordo = min(ys) + 8
            pg.keyboard.press('r')
            for xy in ([180, -40], [220, -20]):          # sul tratto dritto della parete FL1 (da −0,7 a −52,7)
                sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)
                pg.mouse.move(box['x'] + sx, box['y'] + sy)
                pg.mouse.click(box['x'] + sx, box['y'] + sy)
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 7")
            pg.screenshot(path=str(SHOTS / '5_disegno_sviluppo.png'))
            v0 = pg.evaluate('window.__steelcad.state.info.part.volume_mm3')
            pg.click('[data-make="cut"]')
            try:
                pg.wait_for_function('!window.__steelcad.sketch', timeout=15000)
            except Exception:
                print('   taglio non riuscito | toast:', pg.inner_text('#toasts'))
                print('   linee:', pg.evaluate('window.__steelcad.sketch.v.lines.map(l => [l.xa, l.xb])'))
                raise
            st = pg.evaluate('window.__steelcad.state')
            ok(f'tagliato: errori {[e["message"] for e in st["errors"]]}', not st['errors'])
            ok(f'sviluppo con 3 aperture in più ({len(st["sheet"]["data"]["outline"])} contorni)',
               len(st['sheet']['data']['outline']) == 4 + 1)       # + la finestra nella parete FL3
            v1 = st['info']['part']['volume_mm3']
            atteso = math.pi * 100 * 2 + 40 * 20 * 2 + math.sqrt(3) / 4 * 1600 * 2
            ok(f'tolto dal pezzo piegato: {v0 - v1:.1f} mm³ (a mano {atteso:.1f})', abs(v0 - v1 - atteso) < 0.5)
            time.sleep(0.4)
            pg.keyboard.press('0')
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '6_dopo_il_taglio.png'))
            # il bordo tagliato: vista dall'alto sul bordo di FL1
            pg.keyboard.press('u')
            time.sleep(0.5)
            pg.screenshot(path=str(SHOTS / '7_sviluppo_tagliato.png'))
            # da zero: rettangolo scritto 100x50, poi offset di UNA linea (quella sotto) di 15, verso il basso
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['zero', {name: 'Prova'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
            pg.evaluate("window.__steelcad.enterSketch('S1')")
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.5)
            box = pg.locator('#c3d').bounding_box()
            scr = lambda xy: pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)  # noqa: E731
            pg.keyboard.press('r')
            x, y = scr([0, 0])
            pg.mouse.move(box['x'] + x, box['y'] + y); pg.mouse.click(box['x'] + x, box['y'] + y)
            x, y = scr([60, 30])
            pg.mouse.move(box['x'] + x, box['y'] + y)
            ok('rettangolo: la casella chiede larghezza x altezza', 'larghezza x altezza' in pg.inner_text('#sk-cmd'))
            pg.keyboard.type('100x50'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 4')
            xs = pg.evaluate('window.__steelcad.sketch.v.points.map(p => p.xy)')
            ok(f'rettangolo 100 × 50 scritto ({max(p[0] for p in xs)} × {max(p[1] for p in xs)})',
               max(p[0] for p in xs) == 100 and max(p[1] for p in xs) == 50)
            pg.keyboard.press('o')
            pg.keyboard.press('Control+A'); pg.keyboard.type('15'); pg.keyboard.press('Enter')
            x, y = scr([50, 0])
            pg.mouse.move(box['x'] + x, box['y'] + y); pg.mouse.click(box['x'] + x, box['y'] + y)
            x, y = scr([50, -8])
            pg.mouse.move(box['x'] + x, box['y'] + y)
            time.sleep(0.4)
            pg.mouse.click(box['x'] + x, box['y'] + y)
            try:
                pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 5", timeout=8000)
            except Exception:
                print('   offset una linea | toast:', pg.inner_text('#toasts'), '| aiuto:', pg.inner_text('#sk-help'),
                      '| pick:', pg.evaluate("JSON.stringify(window.__steelcad.sketch.pick && {s: window.__steelcad.sketch.pick.stage, ids: window.__steelcad.sketch.pick.ids, d: window.__steelcad.sketch.pick.dist})"),
                      '| linee:', pg.evaluate("window.__steelcad.sketch.v.lines.length"), scr([50, -8]), box)
                pg.screenshot(path=str(SHOTS / 'x_bloccato.png'))
                raise
            nuova = pg.evaluate("window.__steelcad.sketch.v.lines.filter(l => !l.construction).map(l => [l.xa, l.xb])")
            ok(f'offset di una sola linea, 15 sotto: {nuova[-1]}', all(abs(p[1] + 15) < 1e-6 for p in nuova[-1]))
            pg.screenshot(path=str(SHOTS / '8_offset_una_linea.png'))
            pg.keyboard.press('Escape')                      # fine dell'offset

            def clic(xy):
                x, y = scr(xy)
                pg.mouse.move(box['x'] + x, box['y'] + y)
                pg.mouse.click(box['x'] + x, box['y'] + y)

            def linee():
                return pg.evaluate("window.__steelcad.sketch.v.lines.filter(l => !l.construction).map(l => [l.id, l.xa, l.xb])")
            # Taglia: una linea verticale che sborda sopra il rettangolo; clic sul pezzo che sborda
            pg.keyboard.press('l')
            clic([20, 20]); clic([20, 58]); pg.keyboard.press('Escape')
            try:
                pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 6", timeout=6000)
            except Exception:
                print('   linee:', linee(), scr([20, 58]), box, pg.inner_text('#toasts'))
                pg.screenshot(path=str(SHOTS / 'x_linee.png'))
                raise
            vert = next(l for l in linee() if abs(l[1][0] - 20) < 1e-6 and abs(l[2][0] - 20) < 1e-6)
            pg.keyboard.press('t')
            x, y = scr([20, 55])
            pg.mouse.move(box['x'] + x, box['y'] + y)
            time.sleep(0.5)
            ok('Taglia: anteprima rossa sul pezzo che sborda', pg.evaluate('!!window.__steelcad.sketch.cutPrev'))
            pg.screenshot(path=str(SHOTS / '9_taglia_anteprima.png'))
            pg.mouse.click(box['x'] + x, box['y'] + y)
            pg.wait_for_function("(id) => window.__steelcad.sketch.v.lines.some(l => l.id === id && Math.max(l.xa[1], l.xb[1]) < 50.001)", arg=vert[0])
            ok('Taglia: la linea finisce sul lato del rettangolo', True)
            # Allunga: una linea corta dentro il rettangolo; clic vicino all'estremità destra
            pg.keyboard.press('l')
            clic([40, 10]); clic([60, 10]); pg.keyboard.press('Escape')
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 7")
            corta = next(l for l in linee() if abs(l[1][1] - 10) < 1e-6 and abs(l[2][1] - 10) < 1e-6)
            pg.keyboard.press('a')
            clic([58, 10])
            pg.wait_for_function("(id) => window.__steelcad.sketch.v.lines.some(l => l.id === id && Math.max(l.xa[0], l.xb[0]) > 99.999)", arg=corta[0])
            ok('Allunga: la linea arriva al lato destro', True)
            pg.screenshot(path=str(SHOTS / '10_taglia_allunga.png'))

            # asola fatta a mano: due cerchi Ø20, due linee agganciate in cima e in fondo, Taglia le metà dentro
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['zero', {name: 'Asola'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
            pg.evaluate("window.__steelcad.enterSketch('S1')")
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.5)
            box = pg.locator('#c3d').bounding_box()
            pg.keyboard.press('c')
            clic([60, 0]); pg.keyboard.type('20'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.circles.length === 1')
            time.sleep(0.6)                                    # il primo disegno si inquadra da solo
            clic([0, 0]); pg.keyboard.type('20'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.circles.length === 2')
            pg.keyboard.press('l')
            x, y = scr([0.4, 10.3])                            # vicino al punto in cima del primo cerchio
            pg.mouse.move(box['x'] + x, box['y'] + y)
            time.sleep(0.2)
            ok(f'aggancio al quadrante: {pg.inner_text("#sk-tip")!r}', 'in cima del cerchio' in pg.inner_text('#sk-tip'))
            pg.screenshot(path=str(SHOTS / '11_quadrante.png'))
            pg.mouse.click(box['x'] + x, box['y'] + y)
            clic([59.6, 10.2]); pg.keyboard.press('Escape')
            clic([0.3, -10.4]); clic([60.2, -9.7]); pg.keyboard.press('Escape')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 2')
            ends = pg.evaluate('window.__steelcad.sketch.v.lines.map(l => [l.xa, l.xb])')
            ok(f'linee dai quadranti esatti: {ends}', all(abs(abs(p[1]) - 10) < 1e-6 and min(abs(p[0]), abs(p[0] - 60)) < 1e-6 for l in ends for p in l))
            pg.keyboard.press('t')
            clic([10, 0]); time.sleep(0.4)
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 1')
            clic([50, 0])
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 2')
            time.sleep(0.4)
            v = pg.evaluate('window.__steelcad.sketch.v')
            ok(f'asola fatta a mano: contorno chiuso ({v["profiles"]}, {v["status"]})', v['ok'] and v['profiles'] == 1)
            pg.screenshot(path=str(SHOTS / '12_asola_a_mano.png'))
            # strumento Asola: primo centro, interasse 50 scritto, larghezza 12 scritta
            pg.keyboard.press('k')
            clic([0, -25]); x, y = scr([30, -25]); pg.mouse.move(box['x'] + x, box['y'] + y)
            pg.keyboard.type('50'); pg.keyboard.press('Enter')
            ok('Asola: chiede la larghezza', 'Larghezza' in pg.inner_text('#sk-cmd'))
            pg.keyboard.type('12'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 4')
            v = pg.evaluate('window.__steelcad.sketch.v')
            ok(f'Asola 50 × 12 con lo strumento ({v["profiles"]} contorni)', v['profiles'] == 2)

            # agganci: rettangolo 100 × 50 e due cerchi Ø30 (centri 70;25 e 85;25) che si incrociano
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['zero', {name: 'Agganci'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
            pg.evaluate("window.__steelcad.enterSketch('S1')")
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.5)
            box = pg.locator('#c3d').bounding_box()
            pg.keyboard.press('r'); clic([0, 0]); x, y = scr([60, 30]); pg.mouse.move(box['x'] + x, box['y'] + y)
            pg.keyboard.type('100x50'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 4')
            time.sleep(0.6)
            for cx in (70, 85):
                pg.keyboard.press('c'); clic([cx, 25]); pg.keyboard.type('30'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.circles.length === 2')
            box = pg.locator('#c3d').bounding_box()
            (c1, _), (c2, _) = pg.evaluate('window.__steelcad.sketch.v.circles.map(c => [c.xc, c.r])')   # dove sono finiti davvero

            def sopra(xy):
                x, y = scr(xy)
                pg.mouse.move(box['x'] + x, box['y'] + y)
                time.sleep(0.15)
                return pg.evaluate('window.__steelcad.sketch.cursor')
            pg.keyboard.press('l')
            meta = math.dist(c1, c2) / 2
            xi, yi = (c1[0] + c2[0]) / 2, c1[1] + math.sqrt(15 ** 2 - meta ** 2)
            c = sopra([xi + 0.4, yi - 0.4])
            ok(f'incrocio tra due cerchi ({c["tipo"]}, {c["xy"]})', c['tipo'] == 'incrocio' and abs(c['xy'][0] - xi) < 1e-6
               and pg.evaluate("document.querySelector('#sk-snap').style.display") == 'block')
            pg.screenshot(path=str(SHOTS / '13_simbolo_incrocio.png'))
            # tangente dal punto 10;10 al primo cerchio
            clic([10, 10])
            P, C, R = (10, 10), tuple(c1), 15
            d = math.dist(P, C); th = math.atan2(P[1] - C[1], P[0] - C[0]); al = math.acos(R / d)
            T = (C[0] + R * math.cos(th - al), C[1] + R * math.sin(th - al))
            c = sopra([T[0] + 0.3, T[1] + 0.3])
            ok(f'aggancio tangente ({c["tipo"]})', c['tipo'] == 'tangente')
            pg.mouse.click(box['x'] + scr(c['xy'])[0], box['y'] + scr(c['xy'])[1])
            pg.keyboard.press('Escape')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 5')
            tl = next(l for l in pg.evaluate('window.__steelcad.sketch.v.lines') if abs(l['xa'][0] - 10) < 1e-6 or abs(l['xb'][0] - 10) < 1e-6)
            (ax, ay), (bx, by) = tl['xa'], tl['xb']
            dist = abs((bx - ax) * (ay - C[1]) - (ax - C[0]) * (by - ay)) / math.hypot(bx - ax, by - ay)
            ok(f'la linea è davvero tangente (distanza dal centro {dist:.6f} = 15)', abs(dist - 15) < 1e-6)
            # perpendicolare dal punto 40;45 al lato di sotto
            clic([40, 45])
            c = sopra([40.4, 0.3])
            ok(f'aggancio perpendicolare ({c["tipo"]})', c['tipo'] == 'perpendicolare')
            pg.keyboard.press('Escape')
            # puntamento: stessa X del centro del primo cerchio, la linea verde tratteggiata dal centro
            c = sopra([c1[0] + 0.3, 4])
            ok(f'puntamento in verticale dal centro ({c["tipo"]}, {c["how"]})', c['tipo'] == 'punta' and abs(c['xy'][0] - c1[0]) < 1e-6 and len(c['guide']) == 1 and 'dal centro' in c['how'])
            pg.screenshot(path=str(SHOTS / '14_puntamento.png'))
            # F9: senza griglia il punto va dove sei
            pg.keyboard.press('F9')
            c = sopra([33.37, 20.71])
            ok(f'F9 spegne la griglia: punto libero {c["xy"]}', abs(c['xy'][0] - round(c['xy'][0])) > 1e-3 and not pg.evaluate('window.__steelcad.sketch.grid'))
            pg.keyboard.press('F9')

            # strumenti nuovi dalla barra a schede: raccordo, smusso, poligono, arco
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['zero', {name: 'Strumenti'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
            pg.evaluate("window.__steelcad.enterSketch('S1')")
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.5)
            box = pg.locator('#c3d').bounding_box()
            ok('scheda SKETCH accesa', pg.evaluate("!document.querySelector('#rtab-sketch').hidden && document.querySelector('#rtab-sketch').classList.contains('on')"))
            pg.keyboard.press('r'); clic([0, 0]); x, y = scr([60, 30]); pg.mouse.move(box['x'] + x, box['y'] + y)
            pg.keyboard.type('100x50'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 4')
            time.sleep(0.6)
            box = pg.locator('#c3d').bounding_box()
            pg.click('#ribbon [data-tool="fillet"]')
            clic([100, 50])
            ok('Raccordo: chiede il raggio', 'Raggio' in pg.inner_text('#sk-cmd') and pg.evaluate("document.activeElement.id") == 'sk-cmd-in')
            pg.keyboard.press('Control+A'); pg.keyboard.type('10'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 1')
            v = pg.evaluate('window.__steelcad.sketch.v')
            ok(f'raccordo R10 nello spigolo, contorno chiuso ({v["profiles"]})', abs(v['arcs'][0]['r'] - 10) < 1e-6 and v['profiles'] == 1)
            pg.click('#ribbon [data-tool="chamfer"]')
            clic([0, 50]); pg.keyboard.press('Control+A'); pg.keyboard.type('8'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 5')
            ok('smusso 8 nell’altro spigolo', pg.evaluate('window.__steelcad.sketch.v.profiles') == 1)
            pg.click('#ribbon [data-tool="polygon"]')
            pg.click('#sk-cmd-in'); pg.keyboard.press('Control+A'); pg.keyboard.type('5'); pg.keyboard.press('Enter')
            clic([50, 25]); clic([62, 25])
            pg.wait_for_function('window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 10')
            ok('pentagono', True)
            pg.click('#ribbon [data-tool="arc3"]')
            clic([15, 8]); clic([25, 18]); clic([35, 8])
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 2')
            ok('arco per tre punti', True)
            pg.screenshot(path=str(SHOTS / '15_strumenti_nuovi.png'))
            pg.click('#ribbon [data-skdone]')
            pg.wait_for_function('!window.__steelcad.sketch')

            # regole di lamiera e tabella pieghe dalla scheda LAMIERA
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['lamiera', {name: 'Regole', larghezza: 300, profondita: 200, spessore: 2, raggio: 2, k: 0.4}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.objs.has('body')")
            pg.evaluate("fetch('/api/add_flange', {method: 'POST', body: JSON.stringify(['SM1', 'L1', {length: '40'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.length === 1")
            ok('scheda LAMIERA per un progetto in lamiera', pg.evaluate("document.querySelector('[data-rtab=\"lamiera\"]').classList.contains('on')"))
            pg.click('#props [data-azione="altre"]')            # Altre lavorazioni → Regole della piegatrice
            pg.click('#props [data-azione="regole"]')
            pg.wait_for_selector('#r-name')
            pg.fill('#r-name', 'S235 sp. 2 R2 K0,4')
            pg.click('#r-save')
            pg.wait_for_selector('[data-rule-apply]')
            ok('regola salvata e in elenco', 'S235 sp. 2 R2 K0,4' in pg.inner_text('#modal-box'))
            pg.click('#m-no')
            pg.evaluate("fetch('/api/set_sheet_tech', {method: 'POST', body: JSON.stringify(['SM1', {radius: 5}])})")
            time.sleep(0.4); pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.state.sheet.def.radius === 5")
            pg.click('#props [data-azione="altre"]')
            pg.click('#props [data-azione="regole"]')
            pg.wait_for_selector('[data-rule-apply]')
            pg.click('[data-rule-apply]')
            pg.wait_for_function("window.__steelcad.state.sheet.def.radius === 2")
            ok('regola applicata: raggio di nuovo 2', True)
            pg.click('#b-prepara')                              # Prepara per il laser → solo la piegatrice
            pg.wait_for_selector('#modal-box [data-voce="piegatrice"]')
            pg.uncheck('#modal-box [data-voce="laser"]')
            pg.check('#modal-box [data-voce="piegatrice"]')
            pg.click('#m-ok')
            pg.wait_for_selector('.toast:has-text("Salvati 1 file")')
            ok('tabella pieghe da «Prepara per il laser»', True)
            pg.screenshot(path=str(SHOTS / '16_lamiera_barra.png'))
            ok('nessun errore in console', not errori)
            for e in errori:
                print('   console:', e)
            b.close()
    finally:
        srv.kill()
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
