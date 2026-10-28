r"""Prova di tutti i comandi nuovi dell'interfaccia, usati come una persona (mouse e tastiera):
ogni pulsante della barra a schede, cubo delle viste, storia delle operazioni, tema, e il Raccordo nei casi
difficili (spigolo sull'origine, due linee come AutoCAD, linee staccate con R0, smusso).

    <python con playwright> tools\prova_ui_comandi.py cartella_screenshot [--chrome]
"""
import math
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
PORTA = 5095


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
            b = p.chromium.launch(channel='chrome' if '--chrome' in sys.argv else None,
                                  args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))

            def progetto(kind, valori):
                pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
                pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
                pg.evaluate("([k, v]) => fetch('/api/new_project', {method: 'POST', body: JSON.stringify([k, v])})", [kind, valori])
                time.sleep(0.5)
                pg.reload()
                pg.wait_for_function('window.__steelcad && window.__steelcad.ready')
                time.sleep(0.4)

            def scr(xy):
                return pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', xy)

            def clic(xy):
                box = pg.locator('#c3d').bounding_box()
                x, y = scr(xy)
                pg.mouse.move(box['x'] + x, box['y'] + y)
                time.sleep(0.05)
                pg.mouse.click(box['x'] + x, box['y'] + y)

            def v():
                return pg.evaluate('window.__steelcad.sketch.v')

            # ------------------------------------------------ Raccordo: i casi che non andavano
            progetto('zero', {'name': 'Raccordi'})
            pg.evaluate("window.__steelcad.enterSketch('S1')")
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.5)
            pg.keyboard.press('r')
            clic([0, 0])                                        # si aggancia all'origine
            box = pg.locator('#c3d').bounding_box(); x, y = scr([60, 30]); pg.mouse.move(box['x'] + x, box['y'] + y)
            pg.keyboard.type('100x50'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 4')
            time.sleep(0.7)
            pg.click('#ribbon [data-tool="fillet"]')
            clic([0, 0])                                        # lo spigolo sta sopra l'origine
            ok(f'raccordo: lo spigolo sull’origine si sceglie ({pg.inner_text("#sk-cmd")!r})', 'Raggio' in pg.inner_text('#sk-cmd'))
            pg.keyboard.press('Control+A'); pg.keyboard.type('8'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 1', timeout=8000)
            ok(f'raccordo R8 sullo spigolo dell’origine, contorno chiuso ({v()["profiles"]})', v()['profiles'] == 1)
            # due linee, come AutoCAD: lato destro e lato sopra
            clic([100, 25]); clic([60, 50])
            ok('raccordo cliccando due linee: chiede il raggio', 'Raggio' in pg.inner_text('#sk-cmd'))
            pg.keyboard.press('Control+A'); pg.keyboard.type('12'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length === 2', timeout=8000)
            rr = sorted(round(a['r'], 6) for a in v()['arcs'])
            ok(f'raccordo R12 con due linee, contorno chiuso ({rr}, {v()["profiles"]})', rr == [8, 12] and v()['profiles'] == 1)
            ok('resta attivo il Raccordo', pg.evaluate("window.__steelcad.sketch.tool") == 'fillet')
            # smusso sullo spigolo in alto a sinistra
            pg.click('#ribbon [data-tool="chamfer"]')
            clic([0, 50]); pg.keyboard.press('Control+A'); pg.keyboard.type('6'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 5', timeout=8000)
            ok(f'smusso 6 sullo spigolo ({v()["profiles"]} contorno)', v()['profiles'] == 1)
            pg.screenshot(path=str(SHOTS / '1_raccordi.png'))
            # due linee staccate: raggio 0 le unisce in uno spigolo vivo
            pg.keyboard.press('l'); clic([10, 10]); clic([40, 10]); pg.keyboard.press('Escape')
            pg.keyboard.press('l'); clic([60, 20]); clic([60, 40]); pg.keyboard.press('Escape')
            pg.wait_for_function('window.__steelcad.sketch.v.lines.length === 7')
            pg.click('#ribbon [data-tool="fillet"]')
            clic([30, 10]); clic([60, 30])
            pg.keyboard.press('Control+A'); pg.keyboard.type('0'); pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.sketch.v.lines.some(l => Math.abs(l.xb[0] - 60) < 1e-6 && Math.abs(l.xb[1] - 10) < 1e-6 || Math.abs(l.xa[0] - 60) < 1e-6 && Math.abs(l.xa[1] - 10) < 1e-6)", timeout=8000)
            ok('raccordo R0: le due linee staccate si uniscono nello spigolo (60; 10)', True)
            pg.screenshot(path=str(SHOTS / '2_raccordo_r0.png'))
            pg.click('#ribbon [data-skdone]')
            pg.wait_for_function('!window.__steelcad.sketch')

            # ------------------------------------------------ raccordo degli spigoli del pezzo (bordi arancio)
            progetto('lamiera', {'name': 'Spigoli', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
            pg.evaluate(api, ['add_flange', ['SM1', 'L1', {'length': '40'}]])
            sid = pg.evaluate(api, ['sketch_on_face', ['SM1/FL1/esterno']])['sketch']
            pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(0.4)
            pg.evaluate(f"window.__steelcad.enterSketch('{sid}')")
            pg.wait_for_function('window.__steelcad.sketch'); time.sleep(0.5)
            pts = [p['xy'] for p in v()['points'] if p['id'] != 'O']
            angolo = [max(q[0] for q in pts), max(q[1] for q in pts)]
            pg.click('#ribbon [data-tool="fillet"]')
            clic(angolo)
            ok(f'raccordo: lo spigolo del pezzo si sceglie ({pg.inner_text("#sk-cmd")!r})', 'Raggio' in pg.inner_text('#sk-cmd'))
            pg.keyboard.press('Control+A'); pg.keyboard.type('6'); pg.keyboard.press('Enter')
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.some(a => a.ref)', timeout=15000)
            alb = pg.inner_text('#tree')
            ok(f'raccordo R6 sullo spigolo del pezzo: bordo arancio arrotondato e nell’albero ({"Raccordo spigolo R6" in alb})',
               'Raccordo spigolo R6' in alb)
            pg.screenshot(path=str(SHOTS / '2b_raccordo_spigolo_pezzo.png'))
            pg.click('#ribbon [data-skdone]')
            pg.wait_for_function('!window.__steelcad.sketch')

            # ------------------------------------------------ vedi attraverso: i fori della flangia di fronte
            progetto('lamiera', {'name': 'Attraverso', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            pg.evaluate(api, ['add_flange', ['SM1', 'L2', {'length': '50'}]])
            pg.evaluate(api, ['add_flange', ['SM1', 'L4', {'length': '50'}]])
            s1 = pg.evaluate(api, ['sketch_on_face', ['SM1/FL1/esterno']])['sketch']
            pg.evaluate(api, ['sketch_add_circle', [s1, [30, 25], 4]])
            pg.evaluate(api, ['create_from_sketch', [s1, 'cut', {}]])
            s2 = pg.evaluate(api, ['sketch_on_face', ['SM1/FL2/interno']])['sketch']
            pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(0.4)
            pg.evaluate(f"window.__steelcad.enterSketch('{s2}')")
            pg.wait_for_function('window.__steelcad.sketch'); time.sleep(0.5)
            ok('scheda SKETCH: c’è "Vedi attraverso"', pg.is_visible('#rb-xray'))
            pg.keyboard.press('v')
            pg.wait_for_function('window.__steelcad.sketch.v.xray', timeout=15000)
            foro = next((c for c in v()['circles'] if c['xray']), None)
            ok(f'tasto V: il foro dell’altra flangia si vede attraverso ({foro and foro["xc"]})', foro is not None and abs(foro['r'] - 4) < 1e-6)
            pg.keyboard.press('c')
            clic([foro['xc'][0] + 0.3, foro['xc'][1] + 0.2])               # vicino al centro: si aggancia
            pg.keyboard.type('8'); pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.sketch.v.circles.some(c => !c.ref)", timeout=8000)
            nuovo = next(c for c in v()['circles'] if not c['ref'])
            ok(f'cerchio agganciato al centro del foro visto attraverso ({nuovo["xc"]})',
               abs(nuovo['xc'][0] - foro['xc'][0]) < 1e-6 and abs(nuovo['xc'][1] - foro['xc'][1]) < 1e-6)
            pg.screenshot(path=str(SHOTS / '2c_vedi_attraverso.png'))
            pg.keyboard.press('v')
            pg.wait_for_function('!window.__steelcad.sketch.v.xray', timeout=15000)
            ok('di nuovo V: vista attraverso spenta, il cerchio resta', any(not c['ref'] for c in v()['circles']))
            pg.click('#ribbon [data-skdone]')
            pg.wait_for_function('!window.__steelcad.sketch')

            # ------------------------------------------------ lamiera a contorno: la sezione disegnata diventa flange
            progetto('lamiera', {'name': 'Contorno', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            pg.evaluate("""() => { const o = window.__steelcad.objs.get('body');
                const f = o.data.faces.find(x => x.name === 'SM1/lato/L4'); window.__steelcad.select('body', f.index); }""")
            pg.wait_for_selector('[data-face-sketch]')
            pg.click('[data-face-sketch]')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_face === 'SM1/lato/L4'")
            time.sleep(0.6)
            ok('sulla testata c’è il pulsante «Lamiera a contorno»', pg.locator('#sk-contour:not([hidden])').count() == 1)
            pg.keyboard.press('l')
            for xy in ([100, 0], [100, 30], [120, 30], [120, 10], [108, 0]):
                clic(xy)
            pg.keyboard.press('Escape')
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 4")
            ok('stato: la spezzata aperta può diventare lamiera', 'Lamiera a contorno' in pg.inner_text('#sk-status'))
            pg.screenshot(path=str(SHOTS / '0a_sezione.png'))
            pg.click('#sk-more > button'); pg.click('#sk-contour')
            pg.wait_for_function('!window.__steelcad.sketch', timeout=15000)
            st = pg.evaluate('window.__steelcad.state')
            pieghe = [(b['flange'], b['parent'], round(b['length'], 2), round(b['angle'], 1), b['direction']) for b in st['sheet']['data']['bends']]
            ok(f'lamiera a contorno: 4 flange in catena {pieghe}', len(pieghe) == 4 and not st['errors'] and pieghe[0][1] is None
               and [p[1] for p in pieghe[1:]] == [p[0] for p in pieghe[:-1]])
            pg.keyboard.press('0'); time.sleep(0.6)
            pg.screenshot(path=str(SHOTS / '0b_contorno.png'))

            # ------------------------------------------------ aggiungi materiale (linguetta) sulla faccia di una parete
            progetto('lamiera', {'name': 'Linguetta', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            pg.evaluate("fetch('/api/add_flange', {method: 'POST', body: JSON.stringify(['SM1', 'L1', {length: '40'}])})")
            time.sleep(0.5); pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.length === 1")
            pg.evaluate("""() => { const o = window.__steelcad.objs.get('body');
                const f = o.data.faces.find(x => x.name === 'SM1/FL1/esterno'); window.__steelcad.select('body', f.index); }""")
            pg.wait_for_selector('[data-face-sketch]')
            pg.click('[data-face-sketch]')
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_face === 'SM1/FL1/esterno'")
            time.sleep(0.6)
            bordo = max(p['xy'][0] for p in v()['points'] if p['id'] != 'O')
            v0 = pg.evaluate('window.__steelcad.state.info.part.volume_mm3')
            pg.keyboard.press('l')
            for xy in ([bordo, 6], [bordo + 20, 6], [bordo + 20, 30], [bordo, 30]):
                clic(xy)
            pg.keyboard.press('Escape')
            pg.wait_for_function("window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 3")
            pg.click('#sk-tab')
            pg.wait_for_function('!window.__steelcad.sketch', timeout=15000)
            st = pg.evaluate('window.__steelcad.state')
            ok(f'Aggiungi materiale: linguetta 20 × 24 sp. 2 ({st["info"]["part"]["volume_mm3"] - v0:.0f} mm³)',
               not st['errors'] and abs(st['info']['part']['volume_mm3'] - v0 - 20 * 24 * 2) < 1)
            pg.screenshot(path=str(SHOTS / '0c_linguetta.png'))

            # ------------------------------------------------ chiusura della testata di un profilo chiuso
            progetto('lamiera', {'name': 'Profilo', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            for arg in (["SM1", "L1", {"length": "60"}], ["SM1", None, {"length": "40", "direction": "down"}, "FL1"],
                        ["SM1", None, {"length": "40", "direction": "up"}, "FL2"], ["SM1", None, {"length": "40", "direction": "up", "angle": "45"}, "FL3"]):
                pg.evaluate("(a) => fetch('/api/add_flange', {method: 'POST', body: JSON.stringify(a)})", arg)
                time.sleep(0.4)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.length === 4")
            pg.evaluate("window.__steelcad.select('flange=SM1/FL4')")
            pg.wait_for_selector('#props .fhead')
            testo = pg.inner_text('#props').lower()
            ok('pannello flangia pulito: niente "Chiudi la testata" né "Fori"', 'testata' not in testo and 'fori' not in testo)
            # Verso e Misura a pulsanti: un clic e la modifica vale subito
            pg.click('#f-dir button[data-v="down"]')
            pg.wait_for_function("window.__steelcad.state.sheet.data.bends.find(b => b.flange === 'FL4').direction === 'down'", timeout=15000)
            ok('pannello flangia: clic su "fuori" cambia subito il verso', True)
            pg.wait_for_selector('#f-dir button[data-v="down"].on')
            pg.click('#f-dir button[data-v="up"]')
            pg.wait_for_function("window.__steelcad.state.sheet.data.bends.find(b => b.flange === 'FL4').direction === 'up'", timeout=15000)
            pg.wait_for_selector('#f-len')
            pg.fill('#f-len', '45'); pg.keyboard.press('Enter')
            pg.wait_for_function("window.__steelcad.state.sheet.data.bends.find(b => b.flange === 'FL4').length === 45", timeout=15000)
            ok('pannello flangia: lunghezza + Invio, senza "Applica"', True)
            pg.screenshot(path=str(SHOTS / '0_pannello.png'))

            # ------------------------------------------------ ogni pulsante della barra a schede
            progetto('lamiera', {'name': 'Barra', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            pg.evaluate("fetch('/api/add_flange', {method: 'POST', body: JSON.stringify(['SM1', 'L1', {length: '40'}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.state.sheet.data && window.__steelcad.state.sheet.data.bends.length === 1")
            time.sleep(0.4)
            attesi = {
                'new_sheet': 'modal', 'new_zero': 'modal', 'new_frame': 'modal', 'new_free': 'modal',
                'flange_help': 'toast', 'face_help': 'toast', 'contour_help': 'toast', 'member_help': 'toast', 'sheet_rules': 'modal', 'drawings': 'tavole',
                'export_dxf': 'toast', 'export_bendtable': 'toast', 'export_step': 'toast', 'show_cut': 'cut', 'show_bom': 'bom',
                'misura': 'aiuto', 'misura_angolo': 'aiuto',
            }
            ok('progetto in lamiera: si vede solo la scheda LAMIERA',
               pg.evaluate("[...document.querySelectorAll('.rtabs button:not([hidden])')].map(b => b.dataset.rtab).join()") == 'lamiera')
            ok('progetto in lamiera: niente scheda Cut list (non ci sono strutture)',
               pg.evaluate("document.querySelector('.tabs [data-tab=cut]').hidden"))
            for tab in ('lamiera',):
                # nella schermata del pezzo la barra non si vede (c'è "Cosa puoi fare adesso"): i suoi comandi si
                # lanciano per nome, come da Ctrl+K e dai pannelli
                for cmd in pg.evaluate("(t) => [...document.querySelectorAll('.rbody[data-rbody=' + t + '] [data-cmd]')].filter(b => !(b.closest('.drop') && b.hidden)).map(b => (b.closest('.drop') ? 'menu:' : '') + b.dataset.cmd)", tab):
                    # (le voci di Esporta nascoste qui non servono: la distinta Excel c'è solo negli assiemi)
                    if cmd == 'unfold' or cmd == 'flat_sketch':
                        continue                               # provati a parte
                    pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
                    if cmd.startswith('menu:'):                # le voci di Esporta ▾
                        cmd = cmd[5:]
                    pg.evaluate("(c) => window.__steelcad.runCmd(c)", cmd)
                    tipo = attesi.get(cmd, '?')
                    if tipo == 'modal':
                        pg.wait_for_selector('#modal:not([hidden])', timeout=5000)
                        risposta = True
                        pg.keyboard.press('Escape')
                        pg.wait_for_selector('#modal[hidden]', state='attached', timeout=5000)
                    elif tipo == 'tavole':                    # l'editor delle tavole a tutto schermo (25/10)
                        pg.wait_for_selector('#tav-ed', timeout=20000)
                        risposta = True
                        pg.click('#te-chiudi')
                        pg.wait_for_selector('#tav-ed', state='detached', timeout=5000)
                    elif tipo == 'toast':
                        pg.wait_for_selector('.toast', timeout=8000)
                        risposta = pg.locator('.toast.err').count() == 0 or cmd in ('member_help',)
                    elif tipo == 'aiuto':                     # la Quota: si accende e dice cosa cliccare
                        risposta = ('Angolo' if cmd == 'misura_angolo' else 'Quota') in pg.inner_text('#sk-help')
                        pg.evaluate("(c) => window.__steelcad.runCmd(c)", cmd)      # e si spegne
                    elif tipo in ('cut', 'bom'):
                        risposta = pg.evaluate(f"!document.querySelector('#tab-{tipo}').hidden")
                    else:
                        risposta = False
                    testo = pg.inner_text('#toasts')[:70].replace('\n', ' ') if tipo == 'toast' else ''
                    ok(f'barra {tab.upper()} → {cmd}: risponde {testo!r}', risposta)
            ok('schermata del pezzo: comandi nella barra in alto, pannello a destra chiuso',
               pg.is_visible('#ribbon [data-azione="tipo_foro"]') and not pg.is_visible('#right'))
            pg.click('#ribbon [data-cmd="unfold"]')
            pg.wait_for_function('window.__steelcad.look.flat', timeout=20000)   # dopo l'animazione
            time.sleep(0.3)
            ok('barra → Spiega: sviluppo a video', pg.evaluate('window.__steelcad.look.flat'))
            pg.evaluate("window.__steelcad.runCmd('unfold')")
            time.sleep(0.4)
            pg.evaluate("window.__steelcad.runCmd('flat_sketch')")
            pg.wait_for_function("window.__steelcad.sketch && window.__steelcad.sketch.v.on_flat")
            ok('barra → Sullo sviluppo: sketch sullo sviluppo', True)
            pg.click('#ribbon [data-skdone]')
            pg.wait_for_function('!window.__steelcad.sketch')
            time.sleep(0.4)

            # ------------------------------------------------ cubo delle viste, navigazione, storia, tema
            def direzione():
                return pg.evaluate("(() => { const c = window.__steelcad.camera; const d = c.getWorldDirection(new window.__steelcad.THREE.Vector3()); return [d.x, d.y, d.z]; })()")
            for f, atteso in (('pz', (0, 0, -1)), ('ny', (0, 1, 0)), ('px', (-1, 0, 0))):
                pg.click('#viewcube .cube-home'); time.sleep(0.5)     # dall'isometrica si vedono sopra, fronte, destra
                pg.click(f'#cube .cf[data-f="{f}"]')
                d = direzione()
                for _ in range(30):                               # con la grafica software l'animazione è più lenta
                    if all(abs(d[i] - atteso[i]) < 0.05 for i in range(3)):
                        break
                    time.sleep(0.1)
                    d = direzione()
                ok(f'cubo delle viste: faccia {f} → guardo verso {[round(c, 2) for c in d]}', all(abs(d[i] - atteso[i]) < 0.05 for i in range(3)))
            pg.click('#viewcube .cube-home')
            d = direzione()
            for _ in range(30):                                   # l'animazione, con la grafica software
                if d[2] < -0.3 and d[1] > 0.3:
                    break
                time.sleep(0.1)
                d = direzione()
            ok('casetta del cubo: isometrica', d[2] < -0.3 and d[1] > 0.3)
            ok('niente barra "Storia" (ripeteva l’albero)', pg.locator('#tl-items').count() == 0)
            scuro = pg.evaluate("document.body.classList.contains('dark')")
            pg.click('#navbar [data-cmd="toggle_theme"]')
            ok('tema: il pulsante ◐ cambia tema', pg.evaluate("document.body.classList.contains('dark')") != scuro)
            pg.click('#navbar [data-cmd="toggle_theme"]')
            pg.click('#top .menu-item:has-text("File") .tbtn')
            ok('menu File si apre (anche cliccando l’icona)', pg.locator('#top .menu-item.open').count() == 1)
            pg.keyboard.press('Escape'); pg.mouse.click(700, 400)
            pg.click('#palette-btn')
            ok('"Cerca un comando" apre la palette', pg.evaluate("!document.querySelector('#palette').hidden"))
            pg.keyboard.press('Escape')
            # ------------------------------------------------ pagina iniziale
            pg.click('#top .brand')
            pg.wait_for_selector('#home:not([hidden])')
            ok('clic sul logo: pagina iniziale, con "Vai al progetto"', pg.is_visible('#home-close'))
            pg.keyboard.press('Escape')
            ok('Esc torna al progetto', pg.evaluate("document.querySelector('#home').hidden"))
            pg.screenshot(path=str(SHOTS / '3_fine.png'))
            ok('nessun errore in console', not errori)
            for e in errori:
                print('   console:', e)
            b.close()
    finally:
        srv.kill()
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
