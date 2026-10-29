"""Prova dell'interfaccia (29/10): ogni lavorazione si prova sul pezzo prima di farla. La piega su linea senza finestra
(angolo, verso e l'altra parte sono quote sul pezzo), rossa quando non si può (e non si conferma), il taglio con la frase
di cosa toglie. Invio conferma, Esc annulla.

    python tools/prova_ui_anteprime.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5215', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5215/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'P', 'larghezza': 200, 'profondita': 100, 'spessore': 2, 'raggio': 2, 'k': 0.5})

        def sketch(linee, chiuso=False):
            sid = api('sketch_on_flat', 'SM1')['sketch']
            api('sketch_add_polyline', sid, linee, chiuso)
            pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
            pg.evaluate("window.__steelcad.hideHome()")
            pg.evaluate("sid => window.__steelcad.enterSketch(sid)", sid); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
            return sid

        def pronta():
            pg.wait_for_selector('#prova-barra'); pg.wait_for_function("!document.querySelector('#prova-barra').classList.contains('calcolo')", timeout=20000)
            time.sleep(0.4)
            return pg.inner_text('#prova-barra .frase')

        # 1. piega su linea: senza finestra
        sketch([[150, -5], [150, 105]])
        pg.click('#ribbon [data-make="fold"]')
        f = pronta()
        chk('niente finestra: c’è la barra sul pezzo', not pg.is_visible('#modal-box #m-ang'))
        chk('frase: ' + f.replace('\n', ' / '), 'in su di 90°' in f and 'più piccola' in f)
        chk('tre quote sul pezzo (angolo, verso, altra parte)', pg.locator('.quota').count() == 3)
        pg.screenshot(path=str(OUT / '1_piega.png'))
        pg.locator('.quota.blu').first.click(); f = pronta()
        chk('⇅ la gira: ' + f.split('\n')[0], 'in giù' in f)
        pg.locator('.quota').first.click(); time.sleep(0.3)
        pg.click('.q-scelte button:has-text("45°")'); f = pronta()
        chk('angolo dal menu: ' + f.split('\n')[0], '45°' in f)
        pg.keyboard.press('Enter'); time.sleep(2.5)
        st = api('state')
        chk('Invio: piegata', not pg.evaluate("!!window.__steelcad.sketch") and 'Piega in mezzo' in str(st['tree']))
        chk('l’angolo è quello scelto', '45°' in str(st['tree']) and 'giù' in str(st['tree']))

        # 2. rossa: la linea non arriva ai bordi
        sketch([[40, 30], [80, 60]])
        pg.click('#ribbon [data-make="fold"]')
        f = pronta()
        chk('rossa: ' + f.replace('\n', ' / ')[:120], pg.evaluate("document.querySelector('#prova-barra').classList.contains('no')"))
        chk('non si conferma finché è rossa', pg.is_disabled('#pr-ok'))
        pg.screenshot(path=str(OUT / '2_rossa.png'))
        pg.keyboard.press('Enter'); time.sleep(0.5)
        chk('Invio non fa niente', pg.is_visible('#prova-barra'))
        pg.keyboard.press('Escape'); time.sleep(0.5)
        chk('Esc: via la prova, resta lo sketch', not pg.is_visible('#prova-barra') and pg.evaluate("!!window.__steelcad.sketch"))
        pg.evaluate("window.__steelcad.exitSketch()"); time.sleep(1)

        # 3. il taglio si fa subito, senza conferma (29/10)
        sketch([[20, 20], [70, 20], [70, 40], [20, 40]], True)
        pg.click('#ribbon [data-make="cut"]'); time.sleep(2.5)
        chk('taglio subito, senza barra', not pg.is_visible('#prova-barra') and not pg.evaluate("!!window.__steelcad.sketch"))
        chk('tagliato', 'Finestra 50 × 20' in str(api('state')['tree']))
        pg.screenshot(path=str(OUT / '3_taglio.png'))

        # 4. il taglio che non si può fare: barra rossa col motivo
        sketch([[90, 20], [130, 50]])
        pg.click('#ribbon [data-make="cut"]')
        f = pronta()
        chk('taglio impossibile, rossa: ' + f.replace('\n', ' / ')[:120], pg.evaluate("document.querySelector('#prova-barra').classList.contains('no')"))
        pg.screenshot(path=str(OUT / '4_taglio_rosso.png'))
        pg.keyboard.press('Escape'); time.sleep(0.5)
        chk('Esc: resta lo sketch', pg.evaluate("!!window.__steelcad.sketch"))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
