"""Prova dell'interfaccia delle quote comode (05/11, idee da SolidCraft), nel browser senza finestra:

Rettangolo 40 × 20 senza quote dall'origine (può scivolare). Clic sul 40, scrivo 70 senza Invio: lo sketch si allarga
già, dal primo angolo (che resta fermo); Esc torna com'era e l'annulla non ha passi nuovi. Di nuovo sul 40: tasto ↑
(41), Maiusc+↑ (51), freccia ▲ accanto al campo (52), Invio: un passo solo nell'annulla. Trascino il 20 di lato:
il disegno segue, lasciando diventa 30 (un passo). Trascino ed Esc: torna com'era. Tema scuro.

    python tools/prova_ui_quote_comode.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5303
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(tmp)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
while not srv.stdout.readline().startswith(b'http'):
    pass
esiti = []


def ok(t, c):
    esiti.append(bool(c))
    print(('OK   ' if c else 'NO   ') + t, flush=True)


CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])  # noqa: E731
        assert api('new_project', 'zero', {'name': 'Quote comode'})['ok']
        assert api('sketch_add_rectangle', 'S1', [10, 10], [50, 30])['ok']
        for d in api('state')['dimensions']:
            if d['type'] in ('hdistance', 'vdistance'):
                assert api('sketch_delete_dimension', 'S1', d['dim'])['ok']
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.2)
        if pg.is_visible('#home-close'):
            pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", 'S1'); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1.5)
        pg.evaluate("() => window.__steelcad.setTool && window.__steelcad.setTool('select')")

        def punti():
            return {q['id']: q['xy'] for q in pg.evaluate('window.__steelcad.sketch.v.points')}

        def vicino(a, b):
            return abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01

        passi = lambda: pg.evaluate('window.__steelcad.state.storia.qui')  # noqa: E731
        quota = lambda testo: pg.locator('#dims .dim').filter(has_text=testo).first  # noqa: E731
        p0, n0 = punti(), passi()

        # 1. scrivo 70 senza Invio: lo sketch si muove già, dal primo angolo
        quota('40').click(); time.sleep(0.4)
        pg.keyboard.press('Control+A'); pg.keyboard.type('70'); time.sleep(1.0)
        q = punti()
        ok(f'mentre scrivo 70 il lato è già lungo 70 (P2 {q["P2"]})', vicino(q['P2'], (80, 10)))
        ok(f'il primo angolo resta fermo (P1 {q["P1"]})', vicino(q['P1'], (10, 10)))
        ok('il campo è ancora aperto col 70', pg.evaluate("document.activeElement.value") == '70')
        etich = pg.evaluate("[...document.querySelectorAll('#dims .dim')].map(e => e.textContent)")
        ok(f'le frecce su/giù accanto al campo ({etich})', pg.locator('#dims .dim.edit .dim-frecce button').count() == 2)
        pg.screenshot(path=str(out / '1_anteprima_70.png'))
        ok('niente passi nell’annulla durante l’anteprima', passi() == n0)

        # 2. Esc: torna com'era
        pg.keyboard.press('Escape'); time.sleep(0.6)
        q = punti()
        ok(f'Esc: il disegno torna com’era (P2 {q["P2"]})', all(vicino(q[k], p0[k]) for k in p0))
        ok('Esc: annulla senza passi nuovi', passi() == n0 and api('state')['undo'] == pg.evaluate('window.__steelcad.state.undo'))
        ok('Esc: resta nello sketch', pg.evaluate('!!window.__steelcad.sketch'))
        pg.screenshot(path=str(out / '2_esc.png'))

        # 3. frecce: ↑ = 41, Maiusc+↑ = 51, ▲ = 52, Invio
        quota('40').click(); time.sleep(0.4)
        pg.keyboard.press('ArrowUp'); time.sleep(0.15)
        ok(f'tasto ↑: 41 ({pg.evaluate("document.activeElement.value")})', pg.evaluate("document.activeElement.value") == '41')
        pg.keyboard.press('Shift+ArrowUp'); time.sleep(0.15)
        ok(f'Maiusc+↑: 51 ({pg.evaluate("document.activeElement.value")})', pg.evaluate("document.activeElement.value") == '51')
        pg.click('#dims .dim.edit .dim-frecce .su'); time.sleep(0.8)
        val = pg.evaluate("document.querySelector('#dims .dim.edit input')?.value")
        ok(f'freccia ▲: 52, il campo resta attivo ({val})', val == '52' and pg.evaluate("document.activeElement.tagName") == 'INPUT')
        q = punti()
        ok(f'anteprima a 52 (P2 {q["P2"]})', vicino(q['P2'], (62, 10)))
        pg.locator('#dims .dim.edit').screenshot(path=str(out / '3_campo_con_frecce.png'))
        pg.screenshot(path=str(out / '3_frecce_52.png'))
        pg.keyboard.press('ArrowDown'); time.sleep(0.15)
        pg.keyboard.press('ArrowUp'); time.sleep(0.15)
        pg.keyboard.press('Enter'); time.sleep(1.5)
        q = punti()
        ok(f'Invio: il lato è 52 e il primo angolo è fermo ({q["P1"]} → {q["P2"]})', vicino(q['P1'], (10, 10)) and vicino(q['P2'], (62, 10)))
        ok(f'Invio: un passo solo nell’annulla ({n0} → {passi()})', passi() == n0 + 1)

        # 4. trascino il 20 di lato: +60 px = +10 mm
        n1 = passi()
        box = quota('20').bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        pg.mouse.move(x, y); pg.mouse.down()
        for k in range(1, 13):
            pg.mouse.move(x + k * 5 + 1, y); time.sleep(0.03)
        time.sleep(0.8)
        q = punti()
        ok(f'trascinando: l’etichetta dice 30 ({pg.locator("#dims .dim.trascina").text_content()})', pg.locator('#dims .dim.trascina').text_content() == '30')
        ok(f'trascinando: il disegno segue, in su dal primo angolo (P4 {q["P4"]})', vicino(q['P4'], (10, 40)) and vicino(q['P1'], (10, 10)))
        pg.screenshot(path=str(out / '4_trascino_30.png'))
        pg.mouse.up(); time.sleep(1.5)
        q = punti()
        ok(f'lasciato: l’altezza è 30 (P4 {q["P4"]})', vicino(q['P4'], (10, 40)) and vicino(q['P1'], (10, 10)))
        ok(f'lasciato: un passo solo nell’annulla ({n1} → {passi()})', passi() == n1 + 1)
        ok('dopo il trascinamento non si apre il campo', not pg.evaluate("!!document.querySelector('#dims .dim.edit')"))
        pg.screenshot(path=str(out / '5_lasciato_30.png'))

        # 5. trascino ed Esc: torna com'era
        n2, p2 = passi(), punti()
        box = quota('30').bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        pg.mouse.move(x, y); pg.mouse.down()
        for k in range(1, 8):
            pg.mouse.move(x - k * 5 - 1, y); time.sleep(0.03)
        time.sleep(0.8)
        ok(f'trascinando a sinistra cala ({pg.locator("#dims .dim.trascina").text_content()})', pg.locator('#dims .dim.trascina').text_content() == '24')
        pg.keyboard.press('Escape'); time.sleep(0.3); pg.mouse.up(); time.sleep(0.8)
        q = punti()
        ok('Esc mentre trascino: torna com’era, niente passi', all(vicino(q[k], p2[k]) for k in p2) and passi() == n2)
        ok('Esc mentre trascino: resta nello sketch', pg.evaluate('!!window.__steelcad.sketch'))

        # 6. Annulla: la quota trascinata torna a 20
        pg.keyboard.press('Control+z'); time.sleep(1.5)
        q = punti()
        ok(f'Ctrl+Z: l’altezza torna 20 (P4 {q["P4"]})', vicino(q['P4'], (10, 30)))

        # 7. tema scuro: il campo con le frecce
        pg.evaluate("document.body.classList.add('dark')"); time.sleep(0.3)
        quota('52').click(); time.sleep(0.4)
        pg.keyboard.press('ArrowUp'); time.sleep(0.8)
        pg.screenshot(path=str(out / '6_scuro_frecce.png'))
        pg.locator('#dims .dim.edit').screenshot(path=str(out / '6_scuro_campo.png'))
        pg.keyboard.press('Escape'); time.sleep(0.4)
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
