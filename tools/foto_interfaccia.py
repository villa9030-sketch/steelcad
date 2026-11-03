r"""Foto dell'interfaccia: sempre gli stessi stati, con nomi fissi, per confrontare il prima e il dopo di un ritocco.

    <python con playwright> tools\foto_interfaccia.py <cartella_foto> <porta> [--scuro] [--larghezza 1366]

Apre l'app vera senza finestre (server di prova su una cartella temporanea, Chromium headless) e salva:
01_pagina_iniziale, 02_nuovo_pezzo, 03_lamiera_3d, 04_lamiera_selezione, 05_disegno, 06_sviluppo, 07_tubi_telaio,
08_assieme, 09_tavole_editor, 10_prepara, 11_distinta_in_basso, 12_palette_comandi, 13_menu_file.
Una foto che non riesce non ferma le altre: alla fine dice quali mancano.
"""
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
if not PY.exists():
    PY = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad\.venv\Scripts\python.exe')
CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
API = "async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())"
PRONTA = 'window.__steelcad && window.__steelcad.ready'


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    shots, porta = Path(sys.argv[1]), int(sys.argv[2])
    scuro = '--scuro' in sys.argv
    larg = int(sys.argv[sys.argv.index('--larghezza') + 1]) if '--larghezza' in sys.argv else 1500
    alt = 768 if larg <= 1366 else 900
    shots.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='foto_ui_'))
    (tmp / 'lavori').mkdir()
    env = dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp), STEELCAD_RULES=str(tmp / 'regole.json'),
               PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(porta), '--cartella', str(tmp / 'lavori')],
                           cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
    while True:
        riga = srv.stdout.readline()
        if not riga:
            raise SystemExit('il server non parte')
        if riga.startswith(b'http'):
            break
    fatte, mancano, errori = [], [], []
    try:
        with sync_playwright() as p:
            kw = {'args': ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']}
            if Path(CHROME).exists():
                kw['executable_path'] = CHROME
            b = p.chromium.launch(**kw)
            pg = b.new_page(viewport={'width': larg, 'height': alt})
            pg.on('pageerror', lambda e: errori.append(str(e)))
            api = lambda n, *a: pg.evaluate(API, [n, list(a)])  # noqa: E731

            def tema():
                if pg.evaluate("document.body.classList.contains('dark')") != scuro:
                    pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
                    time.sleep(0.4)

            def apri(home=False):
                pg.goto(f'http://127.0.0.1:{porta}/?dev')
                pg.wait_for_function(PRONTA, timeout=60000)
                time.sleep(1.2)
                tema()
                if not home:
                    pg.evaluate("window.__steelcad.hideHome()")
                time.sleep(0.6)

            def fermo():
                time.sleep(0.4)
                try:
                    pg.wait_for_function('!window.__steelcad.state || window.__steelcad.state.scene_version === window.__steelcad.sceneVersion',
                                         timeout=15000)
                except Exception:  # noqa: BLE001 - non tutte le schermate hanno una scena
                    pass
                time.sleep(0.8)

            def foto(nome, fn):
                try:
                    fn()
                    pg.mouse.move(2, alt - 2)          # niente passaggio del mouse rimasto a caso
                    time.sleep(0.3)
                    pg.screenshot(path=str(shots / f'{nome}.png'))
                    fatte.append(nome)
                    print('foto', nome, flush=True)
                except Exception:  # noqa: BLE001 - una foto che non riesce non ferma le altre
                    mancano.append(nome)
                    print('MANCA', nome, traceback.format_exc(limit=2), flush=True)
                    try:
                        pg.keyboard.press('Escape')
                    except Exception:  # noqa: BLE001
                        pass

            # i pezzi che servono, salvati nella cartella temporanea
            pg.goto(f'http://127.0.0.1:{porta}/?dev')
            pg.wait_for_function(PRONTA, timeout=60000)
            L = tmp / 'lavori'
            api('crea_da_modello', 'scatola', {'nome': 'Vaschetta', 'larghezza': 400, 'profondita': 260, 'altezza': 90,
                                               'spessore': 2, 'raggio': 2, 'k': 0.33})
            api('save', str(L / 'Vaschetta.steelcad'))
            api('new_project', 'piastra', {'name': 'Base', 'larghezza': 300, 'altezza': 200, 'spessore': 8, 'foro': 14})
            api('save', str(L / 'Base.steelcad'))
            api('new_project', 'piastra', {'name': 'Piatto', 'larghezza': 160, 'altezza': 80, 'spessore': 5, 'foro': 10})
            api('save', str(L / 'Piatto.steelcad'))
            prima = set(L.glob('*.steelcad'))
            api('new_project', 'telaio', {})
            api('save', True)                     # nel server di prova il file prende il nome del progetto
            nuovi = sorted(set(L.glob('*.steelcad')) - prima)
            TELAIO = nuovi[0] if nuovi else L / 'Banco.steelcad'

            def f01():
                apri(home=True)
                pg.evaluate("window.__steelcad.runCmd('home')")
                time.sleep(1.0)
            foto('01_pagina_iniziale', f01)

            def f02():
                pg.wait_for_selector('#home-modelli [data-mod]', timeout=10000)
                mod = pg.locator('#home-modelli [data-mod="scatola"]')
                (mod if mod.count() else pg.locator('#home-modelli [data-mod]').first).click()
                pg.wait_for_selector('#modal:not([hidden])', timeout=10000)
                time.sleep(0.8)
            foto('02_nuovo_pezzo', f02)

            def f03():
                api('open_path', str(L / 'Vaschetta.steelcad'))
                apri()
                pg.evaluate("window.__steelcad.runCmd('view_iso')")
                fermo()
            foto('03_lamiera_3d', f03)

            def f04():
                box = pg.locator('#c3d').bounding_box()       # clic vero sul fondo della vaschetta, al centro della vista
                x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2 + 10
                pg.mouse.move(x, y)
                time.sleep(0.2)
                pg.mouse.click(x, y)
                pg.wait_for_selector('#mini-barra', timeout=10000)
                time.sleep(0.4)
                piu = pg.locator('#mini-barra button.piu')
                if piu.count():
                    piu.first.click()
                time.sleep(1.0)
            foto('04_lamiera_selezione', f04)

            def f05():
                api('new_project', 'zero', {'name': 'Staffa disegnata'})
                api('sketch_add_rectangle', 'S1', [0, 0], [240, 140])
                api('sketch_add_circle', 'S1', [60, 70], 15)
                api('sketch_add_circle', 'S1', [180, 70], 15)
                apri()
                pg.evaluate("window.__steelcad.enterSketch('S1')")
                pg.wait_for_function('window.__steelcad.sketch', timeout=15000)
                time.sleep(1.0)
                linee = pg.evaluate("window.__steelcad.sketch.v.lines.map(l => l.id)")
                cerchi = pg.evaluate("(window.__steelcad.sketch.v.circles || []).map(c => c.id)")
                for ref in linee[:2]:
                    api('sketch_dimension', 'S1', 'length', [ref])
                if cerchi:
                    api('sketch_dimension', 'S1', 'diameter', [cerchi[0]])
                apri()
                pg.evaluate("window.__steelcad.enterSketch('S1')")
                pg.wait_for_function('window.__steelcad.sketch', timeout=15000)
                time.sleep(1.5)
            foto('05_disegno', f05)

            def f06():
                api('open_path', str(L / 'Vaschetta.steelcad'))
                apri()
                pg.evaluate("window.__steelcad.runCmd('unfold')")
                fermo()
            foto('06_sviluppo', f06)

            def f07():
                api('open_path', str(TELAIO))
                apri()
                pg.evaluate("window.__steelcad.runCmd('view_iso')")
                fermo()
                pg.evaluate("window.__steelcad.select('struct=ST1')")
                pg.wait_for_function('window.__steelcad.nodes.length > 0', timeout=10000)
                nodo = pg.evaluate("(() => { const n = window.__steelcad.nodes; let m = n[0];"
                                   " for (const q of n) if (q.xyz[2] > m.xyz[2] || (q.xyz[2] === m.xyz[2] && q.xyz[0] + q.xyz[1] < m.xyz[0] + m.xyz[1])) m = q;"
                                   " return m.id; })()")
                pg.evaluate("(id) => window.__steelcad.select(id)", nodo)
                time.sleep(1.2)
            foto('07_tubi_telaio', f07)

            def f08():
                api('new_assembly', 'Supporto')
                api('asm_insert', str(L / 'Base.steelcad'))
                api('asm_insert', str(L / 'Piatto.steelcad'))
                api('asm_move', 'I2', 70, 60, 8)
                api('save', str(L / 'Supporto.steelcad-asm'))
                apri()
                pg.evaluate("window.__steelcad.runCmd('view_iso')")
                fermo()
                pg.evaluate("(id) => window.__steelcad.select(id)", 'I2')
                pg.wait_for_selector('#mini-barra', timeout=10000)
                time.sleep(0.4)
                piu = pg.locator('#mini-barra button.piu')
                if piu.count():
                    piu.first.click()
                time.sleep(1.0)
            foto('08_assieme', f08)

            def f09():
                api('open_path', str(L / 'Vaschetta.steelcad'))
                apri()
                pg.evaluate("window.__steelcad.runCmd('drawings')")
                pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=90000)
                time.sleep(1.5)
            foto('09_tavole_editor', f09)

            def f10():
                api('open_path', str(L / 'Vaschetta.steelcad'))
                apri()
                fermo()
                pg.evaluate("window.__steelcad.runCmd('prepara')")
                pg.wait_for_selector('#modal:not([hidden])', timeout=30000)
                time.sleep(2.5)
            foto('10_prepara', f10)

            def f11():
                api('open_path', str(TELAIO))
                apri()
                pg.evaluate("window.__steelcad.runCmd('view_iso')")
                fermo()
                # 04/11: un clic sulla scheda già aperta chiude il cassetto: si clicca la scheda solo se serve
                pg.evaluate("""() => { const b = document.querySelector('#bottom .tabs [data-tab="bom"]');
                    if (document.body.classList.contains('bottom-closed') || !b.classList.contains('on')) b.click(); }""")
                time.sleep(1.0)
            foto('11_distinta_in_basso', f11)

            def f12():
                api('open_path', str(L / 'Vaschetta.steelcad'))
                apri()
                fermo()
                pg.evaluate("window.__steelcad.runCmd('palette')")
                pg.wait_for_selector('#palette:not([hidden])', timeout=5000)
                pg.keyboard.type('pie')
                time.sleep(0.6)
            foto('12_palette_comandi', f12)

            def f13():
                pg.keyboard.press('Escape')
                time.sleep(0.3)
                pg.locator('#top .menu-item > button').first.click()
                time.sleep(0.5)
            foto('13_menu_file', f13)
            b.close()
    finally:
        srv.kill()
    print(f'{len(fatte)} foto in {shots}' + (f'; mancano: {", ".join(mancano)}' if mancano else ''))
    if errori:
        print('errori nella pagina:', *errori[:8], sep='\n  ')
    sys.exit(1 if mancano else 0)


if __name__ == '__main__':
    main()
