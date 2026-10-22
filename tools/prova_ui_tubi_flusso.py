r"""Prova del flusso nuovo dei tubi dall'interfaccia, come una persona (22/10, tela «SteelCAD tubi: flusso nuovo»):
banco fuori tutto → «Cosa puoi fare adesso» → angoli a 45° su tutti → mensola con le frecce → traverso cliccando due
gambe → tubo cliccato con i nomi da officina → sagoma disegnata e «Fai i tubi» → telaio da zero con le frecce.

    .venv\Scripts\python.exe tools\prova_ui_tubi_flusso.py cartella_screenshot     (Edge, già sul PC; niente finestre)
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
PORTA = 5099


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                           env=dict(os.environ, STEELCAD_RULES=str(cart / 'regole.json'), STEELCAD_HOME=str(cart)))
    while not srv.stdout.readline().startswith(b'http'):
        pass
    errori, esiti = [], []

    def ok(cosa, cond):
        esiti.append(bool(cond))
        print(('OK   ' if cond else 'NO   ') + cosa, flush=True)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel='msedge', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            pg.on('console', lambda m: m.type == 'error' and errori.append(m.text))
            pg.on('pageerror', lambda e: errori.append(str(e)))
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
            n = [0]

            def foto(nome):
                n[0] += 1
                time.sleep(0.5)
                pg.screenshot(path=str(SHOTS / f'{n[0]:02d}_{nome}.png'))

            def scena_pronta():
                pg.wait_for_function('window.__steelcad.state.scene_version === window.__steelcad.sceneVersion')
                time.sleep(0.5)

            def pezzi():
                return pg.evaluate('window.__steelcad.state.cutlist.pieces')

            def clic3d(xyz):
                box = pg.locator('#c3d').bounding_box()
                sx, sy = pg.evaluate('(p) => window.__steelcad.toScreen(p)', xyz)
                pg.mouse.move(box['x'] + sx, box['y'] + sy, steps=3)
                pg.mouse.down(); pg.mouse.up()
                time.sleep(0.4)

            def centro(oid, dz=0):
                return pg.evaluate("""([id, dz]) => { const m = window.__steelcad.objs.get(id).mesh; m.geometry.computeBoundingBox();
                    const b = m.geometry.boundingBox; return [(b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, (b.min.z + b.max.z) / 2 + dz]; }""", [oid, dz])

            # 1. banco dalla finestra Nuovo: misure fuori tutto, ripiano sotto
            pg.evaluate("window.__steelcad.nuovo('telaio')")
            foto('banco_finestra')
            testo = pg.inner_text('#modal-box')
            ok('finestra del banco: fuori tutto e ripiano', 'fuori tutto' in testo.lower() and 'Ripiano sotto' in testo)
            pg.click('#n-ok')
            pg.wait_for_function('window.__steelcad.state.cutlist && window.__steelcad.state.cutlist.pieces === 12')
            scena_pronta()
            pg.evaluate("window.__steelcad.select('struct=ST1')")
            pg.wait_for_selector('.cosa-b')
            pannello = pg.text_content('#props')
            ok('appena creato: fuori tutto 1600 × 700 × 850', '1600 × 700 × 850' in pannello)
            ok('«Cosa puoi fare adesso» con traverso, angoli, fori, officina',
               all(x in pannello for x in ('Cosa puoi fare adesso', 'Aggiungi un traverso', 'Come sono saldati gli angoli',
                                           'Fori sui tubi', 'Prepara per l’officina')))
            nomi = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.name)")
            ok('nessuna sigla nei nomi dei tubi', not any(' M1 ' in x or ' G1 ' in x for x in nomi)
               and any(x.startswith('Gamba davanti a sinistra') for x in nomi))
            foto('banco_creato')

            # 2. angoli: dal pulsante, disegnini, 45° su tutti
            pg.click('.cosa-b[data-azione="giunti"]')
            pg.wait_for_selector('.angolo')
            etichette = pg.eval_on_selector_all('.angolo span', 'els => els.map(e => e.textContent)')
            ok(f'angolo con i disegnini: {etichette}', etichette[:2] == ['A 45°', 'Passa la gamba'])
            ok('«uguale su tutti i 4 angoli»', 'tutti i 4 angoli' in pg.inner_text('#props'))
            ok('le 6 frecce intorno all’angolo', pg.locator('.freccia-3d').count() == 6)
            foto('angolo')
            pg.click('.angolo[data-angolo="45"]')
            pg.wait_for_function("window.__steelcad.state.cutlist.rows.some(r => r.length_mm === 1600)")
            scena_pronta()
            ok('A 45° su tutti: traversi lunghi 1600 a 45°', True)

            # 3. mensola con la freccia Sinistra (dall'angolo davanti a sinistra, in alto)
            nodo = pg.evaluate("window.__steelcad.nodes.find(n => n.xyz[0] === 0 && n.xyz[1] === 0 && n.xyz[2] === 850).id")
            pg.evaluate("(id) => window.__steelcad.select(id)", nodo)
            pg.wait_for_selector('#n-len')
            pg.fill('#n-len', '300')
            pg.fill('#n-nome', 'Mensola')
            pg.click('.freccia-3d:has-text("Sinistra")')
            pg.wait_for_function('window.__steelcad.state.cutlist.pieces === 13')
            scena_pronta()
            nomi = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.name)")
            ok('mensola da 300 con il suo nome', any(x.startswith('Mensola') and '300' in x for x in nomi))
            foto('mensola')

            # 4. traverso cliccando le due gambe davanti
            pg.evaluate("window.__steelcad.select('struct=ST1')")
            pg.wait_for_selector('.cosa-b[data-azione="traverso"]')
            pg.click('.cosa-b[data-azione="traverso"]')
            pg.wait_for_selector('#trav-hint:not([hidden])')
            gambe = pg.evaluate("[...window.__steelcad.objs.values()].filter(o => /^Gamba davanti/.test(o.data.name)).map(o => o.data.id)")
            clic3d(centro(gambe[0]))
            clic3d(centro(gambe[1]))
            pg.wait_for_selector('#tr-q')
            ok('traverso: «Altezza da terra» con sotto / metà / sopra', 'Altezza da terra' in pg.inner_text('#props')
               and pg.locator('[data-rif]').count() == 3)
            pg.fill('#tr-q', '400')
            foto('traverso')
            pg.click('#tr-ok')
            pg.wait_for_function('window.__steelcad.state.cutlist.pieces === 15')
            scena_pronta()
            nomi = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.name)")
            ok('2 traversi a 400 da terra (davanti e dietro)',
               sum(1 for x in nomi if 'a 400 da terra' in x) == 2)

            # 5. clic su un tubo: il pannello da officina
            pg.evaluate("(id) => window.__steelcad.select(id)", gambe[0])
            pg.wait_for_selector('#p-trav')
            pannello = pg.inner_text('#props')
            ok('tubo: nome, «Da tagliare», «Traverso da qui», «Togli questo tubo»',
               pannello.startswith('Gamba davanti') and 'Da tagliare' in pannello and 'Traverso da qui' in pannello
               and 'Togli questo tubo' in pannello and 'Linea d’asse' not in pannello)
            foto('tubo')

            # 6. sagoma disegnata nel progetto e «Fai i tubi»
            pg.evaluate("window.__steelcad.nuovo('disegno')")
            pg.click('#n-ok')
            pg.wait_for_function('window.__steelcad.sketch')
            time.sleep(0.8)
            ok('sagoma: c’è «Fai i tubi» e non «Crea lamiera»', pg.is_visible('#sk-tubi') and not pg.is_visible('#sk-make [data-make="sheet"]'))
            c3d = pg.locator('#c3d').bounding_box()

            def punto(x, y):
                sx, sy = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [x, y])
                pg.mouse.move(c3d['x'] + sx, c3d['y'] + sy, steps=3)
                pg.mouse.down(); pg.mouse.up()
                time.sleep(0.25)
            pg.keyboard.press('l')
            for x, y in ((0, 0), (0, 400), (600, 400), (600, 0)):
                punto(x, y)
            pg.keyboard.press('Escape')
            pg.wait_for_function('window.__steelcad.sketch && window.__steelcad.sketch.v.lines.filter(l => !l.construction).length === 3')
            foto('sagoma')
            pg.click('#sk-tubi')
            pg.wait_for_selector('#ft-d')
            pg.fill('#ft-p', '30x30x2')
            pg.fill('#ft-d', '500')
            pg.fill('#ft-cp', '30x30x2')
            pg.click('#m-ok')
            pg.wait_for_function('!window.__steelcad.sketch && window.__steelcad.state.cutlist && window.__steelcad.state.cutlist.pieces === 10')
            scena_pronta()
            ok('sagoma a U ripetuta a 500 e collegata: 10 tubi', True)
            foto('sagoma_tubi')

            # 7. telaio da zero con le frecce
            pg.evaluate("window.__steelcad.nuovo('vuoto')")
            pg.click('#n-ok')
            pg.wait_for_function("window.__steelcad.nodes.length === 1")
            pg.evaluate("window.__steelcad.select(window.__steelcad.nodes[0].id)")
            pg.wait_for_selector('.freccia-3d')
            pg.fill('#n-len', '1600')
            pg.click('.freccia-3d:has-text("Destra")')
            pg.wait_for_function('window.__steelcad.state.cutlist && window.__steelcad.state.cutlist.pieces === 1')
            scena_pronta()
            pg.wait_for_function("document.querySelector('#props h3') && /Angolo|Punto/.test(document.querySelector('#props h3').textContent)")
            time.sleep(0.5)
            pg.fill('#n-len', '700')
            pg.click('.freccia-3d:has-text("Dietro")')
            pg.wait_for_function('window.__steelcad.state.cutlist.pieces === 2')
            scena_pronta()
            nomi = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.name)")
            ok(f'da zero: due tubi con le frecce {nomi}', any(x.startswith('Traverso davanti') and x.endswith('1600') for x in nomi)
               and any(x.startswith('Fianco a destra') and x.endswith('700') for x in nomi))
            foto('da_zero')
            ok(f'nessun errore nella pagina {errori[:3]}', not errori)
            b.close()
    finally:
        srv.kill()
    print(f'{sum(esiti)}/{len(esiti)} controlli')
    sys.exit(0 if all(esiti) else 1)


if __name__ == '__main__':
    main()
