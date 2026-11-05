r"""Prova della «Lamiera forata» (05/11), come una persona: lamiera 400 × 300 sp. 2 piegata a 60 su un lato.
Clic sulla faccia di sopra, «Lamiera forata» nella barra, fori Ø5 sfalsati passo 10, margine 15: anteprima (i fori in
arancio sulla faccia e quanti sono), Fai. Poi lo sviluppo. Poi asole sulla faccia piegata (fila), di nuovo lo sviluppo
(i fori della piega ci devono essere). Poi si cambia dal pannello (Ø6). Tema scuro. Infine 2000 fori: non deve bloccarsi.

    <python con playwright> tools\prova_ui_forata.py cartella_screenshot [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando  # noqa: F401  (comandi della barra, anche nei menu dei gruppi)
from prova_ui_foro import CENTRO_FACCIA

ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or ROOT / '.venv' / 'Scripts' / 'python.exe')
SHOTS = Path(sys.argv[1])
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5304
CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
FORATA = '[data-rbody="lamiera"] [data-azione="forata"]'


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
            api('new_project', 'lamiera', {'larghezza': 400, 'profondita': 300, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            api('add_flange', 'SM1', 'L1', {'length': '60'})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            canvas = pg.locator('#c3d').bounding_box()

            def clic_faccia(nome):
                x, y = pg.evaluate(CENTRO_FACCIA, [nome])
                pg.mouse.click(canvas['x'] + x, canvas['y'] + y)
                time.sleep(0.8)

            def aspetta_frase(testo, foto):
                try:
                    pg.wait_for_function(f"document.getElementById('lf-frase')?.textContent.includes({testo!r})", timeout=30000)
                except Exception:
                    pg.screenshot(path=str(SHOTS / foto))
                    print('FINESTRA:', pg.locator('#modal-box').inner_text(), errori)
                    raise
                time.sleep(0.6)

            def fai():
                # finito quando il pezzo nuovo è arrivato e si vede: la scena è cambiata e coincide con lo stato
                prima = pg.evaluate('window.__steelcad.sceneVersion')
                t0 = time.perf_counter()
                pg.locator('#m-ok').click()
                pg.wait_for_function("document.getElementById('modal').hidden", timeout=30000)
                pg.wait_for_function(f"window.__steelcad.sceneVersion > {prima} && window.__steelcad.sceneVersion === window.__steelcad.state.scene_version"
                                     " && !document.querySelector('#attesa:not([hidden])')", timeout=120000)
                return time.perf_counter() - t0

            # 1) faccia di sopra, «Lamiera forata» nella barra
            clic_faccia('SM1/sopra')
            pg.keyboard.press('Escape')
            comando(pg, FORATA)
            pg.wait_for_selector('#lf-d', timeout=20000)
            aspetta_frase('fori', '01x_errore.png')
            pg.screenshot(path=str(SHOTS / '01_forata_aperta.png'))
            pg.locator('#lf-d').fill('5')
            pg.locator('#lf-d').dispatch_event('input')
            pg.locator('#lf-px').fill('10')
            pg.locator('#lf-px').dispatch_event('input')
            pg.locator('#lf-margine').fill('15')
            pg.locator('#lf-margine').dispatch_event('input')
            aspetta_frase('passo 10', '02x_errore.png')
            pg.wait_for_function("window.__steelcad.forata > 0", timeout=20000)
            frase = pg.locator('#lf-frase').inner_text()
            print('frase:', frase)
            ok('anteprima: quanti fori, Ø5, sfalsati, ponticello', 'fori Ø5' in frase and 'sfalsati' in frase and 'ponticello 5 mm' in frase)
            ok('anteprima disegnata sulla faccia', pg.evaluate('window.__steelcad.forata') > 1000)
            n_ant = int(frase.split(' ')[0])
            ok('il pulsante dice quanti', pg.locator('#m-ok').inner_text() == f'Fai: {n_ant} fori')
            pg.screenshot(path=str(SHOTS / '02_anteprima_fori.png'))
            dt = fai()
            print(f'fatti in {dt:.1f} s')
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '03_fori_fatti.png'))
            albero = pg.locator('#tree').inner_text()
            ok(f'albero: «Lamiera forata: {n_ant} fori Ø5 sfalsati»', f'{n_ant} fori Ø5 sfalsati' in albero)
            # lo sviluppo
            comando(pg, '[data-rbody="lamiera"] [data-cmd="unfold"]')
            time.sleep(2.5)
            pg.screenshot(path=str(SHOTS / '04_sviluppo_fori.png'))
            comando(pg, '[data-rbody="lamiera"] [data-cmd="unfold"]')
            time.sleep(2.5)

            # 2) asole sulla faccia piegata, in fila, dalle azioni della faccia
            pg.evaluate("window.__steelcad.runCmd('view_iso')")
            time.sleep(1.5)
            clic_faccia('SM1/FL1/esterno')
            pg.screenshot(path=str(SHOTS / '05_faccia_piegata.png'))
            if pg.locator('#props [data-azione="forata"]').count():
                pg.locator('#props [data-azione="forata"]').first.click()
            else:
                comando(pg, FORATA)
            pg.wait_for_selector('#lf-corpo', timeout=20000)
            ok('finestra sulla faccia piegata', 'piega' in pg.locator('#lf-tit').inner_text())
            print('titolo:', pg.locator('#lf-tit').inner_text())
            pg.locator('[data-lf-seg="forma"] [data-v="asola"]').click()
            pg.wait_for_selector('#lf-lung', timeout=5000)
            pg.locator('[data-lf-seg="disposizione"] [data-v="fila"]').click()
            pg.wait_for_selector('#lf-py', timeout=5000)
            for k, val in (('lung', '20'), ('larg', '6'), ('px', '30'), ('py', '14'), ('margine', '8')):
                pg.locator(f'#lf-{k}').fill(val)
                time.sleep(0.2)
            aspetta_frase('asole 20 × 6, in fila, passo 30 × 14', '06x_errore.png')
            pg.screenshot(path=str(SHOTS / '06_asole_anteprima.png'))
            n_as = int(pg.locator('#lf-frase').inner_text().split(' ')[0])
            fai()
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '07_asole_fatte.png'))
            comando(pg, '[data-rbody="lamiera"] [data-cmd="unfold"]')
            time.sleep(2.5)
            pg.screenshot(path=str(SHOTS / '08_sviluppo_con_la_piega.png'))
            st = api('state')
            fori_svil = sum(1 for w in (st.get('sheet') or {}).get('data', {}).get('outline', [])[1:])
            print('contorni interni nello sviluppo:', fori_svil, 'attesi', n_ant + n_as)
            ok('lo sviluppo ha tutti i fori (anche della piega)', fori_svil == n_ant + n_as)
            comando(pg, '[data-rbody="lamiera"] [data-cmd="unfold"]')
            time.sleep(2.5)

            # 3) si cambia dopo: dal pannello
            pg.evaluate("window.__steelcad.runCmd('view_iso')")
            time.sleep(1.0)
            pg.evaluate("window.__steelcad.select('lf=LF1')")
            pg.wait_for_selector('#lf-cambia', timeout=20000)
            time.sleep(0.8)
            pg.screenshot(path=str(SHOTS / '09_pannello.png'))
            pg.locator('#lf-cambia2').click()
            pg.wait_for_selector('#lf-d', timeout=20000)
            ok('si riapre con com’era (Ø5)', pg.locator('#lf-d').input_value() == '5')
            pg.locator('#lf-d').fill('6')
            pg.locator('#lf-d').dispatch_event('input')
            aspetta_frase('Ø6', '10x_errore.png')
            pg.screenshot(path=str(SHOTS / '10_cambia_anteprima.png'))
            ok('cambio: pulsante «Cambia»', pg.locator('#m-ok').inner_text().startswith('Cambia'))
            fai()
            time.sleep(1.0)
            albero = pg.locator('#tree').inner_text()
            ok('albero aggiornato: Ø6', 'fori Ø6 sfalsati' in albero)

            # 4) tema scuro, con la finestra aperta
            pg.click('#navbar [data-cmd="toggle_theme"]') if pg.locator('#navbar [data-cmd="toggle_theme"]').count() else pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
            time.sleep(0.8)
            comando(pg, FORATA)
            pg.wait_for_selector('#lf-corpo', timeout=20000)
            time.sleep(1.5)
            pg.screenshot(path=str(SHOTS / '11_scuro_finestra.png'))
            pg.keyboard.press('Escape')
            time.sleep(0.5)
            pg.evaluate("window.__steelcad.runCmd('toggle_theme')")
            time.sleep(0.5)

            # 5) solo dentro un contorno disegnato: un cerchio R60 sulla faccia, «Altro ▾ → Lamiera forata qui dentro»
            api('new_project', 'lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
            sid = api('sketch_on_face', 'SM1/sopra')['sketch']
            api('sketch_add_circle', sid, [150, 100], 60)
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            pg.evaluate(f"window.__steelcad.enterSketch({sid!r})")
            pg.wait_for_function("window.__steelcad.sketch", timeout=20000)
            time.sleep(1.5)
            comando(pg, '#sk-forata')
            pg.wait_for_selector('#lf-corpo', timeout=20000)
            aspetta_frase('fori', '14x_errore.png')
            ok('zona: dentro il disegno, già scelta', pg.locator(f'[data-lf-seg="sketch"] button.on[data-v="{sid}"]').count() == 1)
            ok('zona: dice «Margine dal bordo della faccia»', 'Margine dal bordo della faccia' in pg.locator('#lf-corpo').inner_text())
            pg.screenshot(path=str(SHOTS / '14_dentro_il_cerchio.png'))
            n_z = int(pg.locator('#lf-frase').inner_text().split(' ')[0])
            fai()
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '15_dentro_il_cerchio_fatto.png'))
            ok(f'zona: {n_z} fori fatti dentro il cerchio', f'{n_z} fori' in pg.locator('#tree').inner_text())

            # 6) 2000 fori
            api('new_project', 'lamiera', {'larghezza': 600, 'profondita': 400, 'spessore': 1.5, 'raggio': 1.5, 'k': 0.4})
            pg.reload()
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=150000)
            pg.evaluate('window.__steelcad.hideHome && window.__steelcad.hideHome()')
            time.sleep(1.0)
            comando(pg, FORATA)
            pg.wait_for_selector('#lf-d', timeout=20000)
            t0 = time.perf_counter()
            pg.locator('#lf-px').fill('11')
            pg.locator('#lf-px').dispatch_event('input')
            aspetta_frase('passo 11', '12x_errore.png')
            t_ant = time.perf_counter() - t0
            n_big = int(pg.locator('#lf-frase').inner_text().split(' ')[0])
            print(f'anteprima di {n_big} fori in {t_ant:.1f} s')
            ok('anteprima di 2000 fori in meno di 3 s', n_big > 2000 and t_ant < 3)
            pg.screenshot(path=str(SHOTS / '12_duemila_anteprima.png'))
            dt = fai()
            print(f'{n_big} fori fatti e mostrati in {dt:.1f} s')
            ok('2000 fori fatti e mostrati in meno di 25 s', dt < 25)
            time.sleep(1.0)
            pg.screenshot(path=str(SHOTS / '13_duemila_fatti.png'), timeout=180000)   # 260 mila triangoli col disegno software
            b.close()
    finally:
        srv.terminate()
    print('errori console:', errori)
    print(f'{sum(esiti)}/{len(esiti)} ok')


if __name__ == '__main__':
    main()
