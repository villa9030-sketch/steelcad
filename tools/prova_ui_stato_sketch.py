r"""Prova a schermo dello stato del disegno (05/11, idee da SolidCraft).

1. Quanto manca: un rettangolo quotato dall'origine è «Tutto definito»; una spezzata in più senza quote fa «Mancano
   2 misure» e le sue linee diventano blu.
2. Estremità aperte: un contorno che non torna sul primo punto per mezzo millimetro: pallini rossi, cerchio giallo
   sulla coppia vicina, «Chiudi» lo chiude.
3. Sistema il disegno: piastra 300 × 200 con raggi R20 dal DXF del cliente (punti bloccati): anteprima con
   orizzontali/verticali (arancio), uguali (viola), tangenze (pallini blu); poi «Mancano 3 misure».
4. Importa SVG: un logo largo 170 mm al centro della lamiera, anteprima tratteggiata, poi «Tutto definito».
5. Tema scuro.

    <python con playwright> tools\prova_ui_stato_sketch.py cartella_screenshot [porta]
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
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5326
CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'

LOGO = '''<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 200 100">
<path d="M10 10 L60 10 C 70 10 80 20 80 30 A 20 20 0 0 1 60 50 L10 50 Z"/>
<circle cx="120" cy="35" r="10"/><rect x="140" y="15" width="40" height="40" rx="6"/>
<path d="M95 60 C 110 45 140 75 160 58 L 175 58 L 175 62 C 150 80 115 50 95 64 Z"/>
<text x="1" y="1">RADIUS</text></svg>'''


def piastra_dxf(cart):
    import ezdxf
    d = ezdxf.new()
    d.header['$INSUNITS'] = 4
    b = 0.4142135623730951
    d.modelspace().add_lwpolyline([(20, 0, 0), (280, 0, b), (300, 20, 0), (300, 180, b), (280, 200, 0),
                                   (20, 200, b), (0, 180, 0), (0, 20, b)], close=True, format='xyb')
    p = cart / 'piastra_cliente.dxf'
    d.saveas(p)
    return p


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

            def entra(sid='S1'):
                pg.reload()
                pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
                pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
                pg.evaluate('(s) => window.__steelcad.enterSketch(s)', sid)
                time.sleep(1.5)

            v = lambda: pg.evaluate('window.__steelcad.sketch.v')  # noqa: E731
            stato = lambda: pg.locator('#sk-stato').inner_text().replace('\n', ' ')  # noqa: E731

            # ---------------------------------------------------------------- 1. quanto manca
            api('new_project', 'zero', {'name': 'Prova stato'})
            api('sketch_add_rectangle', 'S1', 'O', [250, 120])
            entra()
            print('stato:', stato())
            ok('rettangolo quotato: «Tutto definito»', 'Tutto definito' in stato())
            ok('niente linee blu', not pg.locator('#sk-leg-liberi').is_visible())
            pg.screenshot(path=str(SHOTS / '01_tutto_definito.png'))
            r = api('sketch_add_polyline', 'S1', [[320, 20], [420, 60], [470, 10]], False)
            ok('spezzata in più', r.get('ok'))
            entra()
            print('stato:', stato())
            ok('«Mancano 2 misure» (le linee sciolte restano rosse)', 'Mancano 2 misure' in stato())
            ok('le due linee nuove sono le libere', len(v()['misure']['liberi']) == 2)
            ok('le estremità della spezzata: 2 aperte', '2 estremità aperte' in stato())
            pg.screenshot(path=str(SHOTS / '02_mancano_misure_linee_blu.png'))

            # ---------------------------------------------------------------- 2. estremità aperte, Chiudi
            api('new_project', 'zero', {'name': 'Contorno aperto'})
            api('sketch_add_polyline', 'S1', [[0, 0], [200, 0], [200, 120], [60, 160], [0.4, 120], [0.0, 0.6]], False)
            entra()
            print('stato:', stato())
            ok('2 estremità aperte e «Chiudi»', '2 estremità aperte' in stato() and pg.locator('#sk-chiudi').is_visible())
            ok('nessun contorno chiuso', v()['profiles'] == 0)
            # vicino all'angolo, per vedere i pallini
            box = pg.locator('#c3d').bounding_box()
            x, y = pg.evaluate('(xy) => window.__steelcad.skScreen(xy)', [0, 0])
            pg.screenshot(path=str(SHOTS / '03_estremita_aperte.png'))
            pg.mouse.move(box['x'] + x, box['y'] + y)
            for _ in range(8):
                pg.mouse.wheel(0, -300)
                time.sleep(0.08)
            time.sleep(0.6)
            pg.screenshot(path=str(SHOTS / '03b_pallini_da_vicino.png'))
            pg.locator('#sk-chiudi').click()
            pg.wait_for_function('!window.__steelcad.sketch.v.aperte.length', timeout=20000)
            time.sleep(0.8)
            print('dopo Chiudi:', stato(), '|', pg.locator('#toasts').inner_text().replace('\n', ' ')[:200])
            ok('chiuso: un contorno, niente estremità aperte', v()['profiles'] == 1 and not pg.locator('#sk-chiudi').is_visible())
            pg.screenshot(path=str(SHOTS / '04_chiuso.png'))

            # ---------------------------------------------------------------- 3. Sistema il disegno (DXF)
            dxf = piastra_dxf(cart)
            r = api('import_dxf', str(dxf))
            r = api('import_dxf_create', r['scelto'], {'thickness': 3, 'radius': 3, 'k': 0.4, 'material': 'S235'})
            ok('DXF importato', r.get('ok'))
            entra('S1')
            print('stato DXF:', stato())
            comando(pg, '#ribbon [data-act="sistema"]')
            pg.wait_for_selector('#sd-tipi', timeout=20000)
            time.sleep(0.8)
            testo = pg.locator('#modal-box').inner_text().replace('\n', ' / ')
            print('sistema:', testo)
            ok('anteprima: 4 orizzontali e verticali, 8 tangenti, 3 uguali', pg.evaluate("[...document.querySelectorAll('#sd-tipi b')].map(x => x.textContent).join(',')") == 'nessuno,4,8,3')
            ok('«Dopo: mancano 3 misure»', 'mancano 3 misure' in pg.locator('#sd-frase').inner_text())
            ok('segni in prova', len(pg.evaluate('window.__steelcad.sketch.sistemaProva.hv')) == 4)
            pg.screenshot(path=str(SHOTS / '05_sistema_anteprima.png'))
            pg.locator('#sd-tipi [data-sd="uguali"]').uncheck()
            pg.wait_for_function("document.getElementById('sd-frase').textContent.includes('6 misure')", timeout=20000)
            ok('senza uguali: «mancano 6 misure» (si aggiorna mentre scegli)', True)
            pg.locator('#sd-tipi [data-sd="uguali"]').check()
            pg.wait_for_function("document.getElementById('sd-frase').textContent.includes('3 misure')", timeout=20000)
            pg.locator('#m-ok').click()
            pg.wait_for_function("document.getElementById('sk-misure').textContent.includes('3 misure')", timeout=20000)
            time.sleep(0.6)
            print('dopo Sistema:', stato(), '|', pg.locator('#toasts').inner_text().replace('\n', ' ')[:200])
            ok('«Mancano 3 misure», linee blu', 'Mancano 3 misure' in stato() and len(v()['misure']['liberi']) == 8)
            pg.screenshot(path=str(SHOTS / '06_sistemato.png'))

            # ---------------------------------------------------------------- 4. Importa SVG
            (cart / 'logo.svg').write_text(LOGO, encoding='utf-8')
            api('new_project', 'lamiera', {'larghezza': 300, 'profondita': 300, 'spessore': 2})
            sc = api('scene')
            faccia = next(x for x in sc['objects'][0]['faces'] if x['name'] and x['name'].endswith('sopra'))
            sid = api('sketch_on_face', faccia['name'])['sketch']
            entra(sid)
            comando(pg, '#ribbon [data-act="svg"]')
            pg.wait_for_selector('#sv-form', timeout=20000)
            pg.locator('#sv-w').fill('170')
            pg.locator('#sv-dove').select_option('1')
            pg.locator('#sv-x').fill('150')
            pg.locator('#sv-y').fill('150')
            pg.locator('#sv-y').dispatch_event('input')
            pg.wait_for_function("document.getElementById('sv-frase').textContent.includes('170')", timeout=20000)
            time.sleep(0.8)
            testo = pg.locator('#modal-box').inner_text().replace('\n', ' / ')
            print('svg:', testo)
            ok('dice del testo da convertire', 'converti in curve' in testo)
            ok('anteprima in prova', len(pg.evaluate('window.__steelcad.sketch.svgProva')) > 3)
            pg.screenshot(path=str(SHOTS / '07_svg_anteprima.png'))
            pg.locator('#m-ok').click()
            pg.wait_for_function('window.__steelcad.sketch.v.arcs.length > 3', timeout=30000)
            time.sleep(1.0)
            print('dopo SVG:', stato(), '|', pg.locator('#toasts').inner_text().replace('\n', ' ')[:200])
            ok('importato: «Tutto definito», 4 contorni chiusi', 'Tutto definito' in stato() and v()['profiles'] == 4)
            pg.screenshot(path=str(SHOTS / '08_svg_importato.png'))
            r = api('create_from_sketch', sid, 'cut', {})
            ok('si taglia', r.get('ok'))

            # ---------------------------------------------------------------- 5. tema scuro
            api('new_project', 'zero', {'name': 'Scuro'})
            api('sketch_add_rectangle', 'S1', 'O', [250, 120])
            api('sketch_add_polyline', 'S1', [[320, 20], [420, 60], [470, 10], [320.5, 20.4]], False)
            entra()
            if not pg.evaluate("document.body.classList.contains('dark')"):
                pg.evaluate("document.querySelector('#navbar [data-cmd=\"toggle_theme\"]').click()")
            time.sleep(0.8)
            ok('tema scuro', pg.evaluate("document.body.classList.contains('dark')"))
            pg.screenshot(path=str(SHOTS / '09_tema_scuro.png'))
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
