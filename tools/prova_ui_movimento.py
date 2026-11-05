"""Prova dell'interfaccia dei pezzi che si muovono (05/11) nel browser senza finestra: l'anta dell'ufficio
(tests/data/vano/anta.steelcad, tubi 40×40) su un pilastro 80 × 80 alto 2200, con 2 mm di luce. «Cerniera», clic
sullo spigolo davanti a sinistra dell'anta (l'asse tratteggiato), clic sul pilastro → pannello del giunto. Scrive 45
(a metà corsa, anteprima mentre scrive) poi 90 e Invio; trascina col mouse; «Trova da solo»; «Controlla che non
sbatta» col punto rosso; «Torna com'era»; tema scuro. Screenshot nella cartella.

    python tools/prova_ui_movimento.py [cartella_screenshot] [porta]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5321
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'anta.steelcad', cart / 'ANTA UFFICIO.steelcad')
d = json.loads((ROOT / 'tests' / 'data' / 'vano' / 'plexi.steelcad').read_text(encoding='utf-8'))
d['meta']['name'] = 'PILASTRO'
d['parameters'] = {'W': 80, 'P': 80, 'sp': 2200}
d['material'] = 'S235'
(cart / 'PILASTRO.steelcad').write_text(json.dumps(d), encoding='utf-8')
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
while not srv.stdout.readline().startswith(b'http'):
    pass
esiti = []


def ok(t, c):
    esiti.append(bool(c))
    print(('OK   ' if c else 'NO   ') + t, flush=True)


CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        if os.environ.get('MV_DEBUG'):
            pg.on('request', lambda q: print('REQ', q.url[-30:], (q.post_data or '')[:300]) if 'giunto' in q.url or 'add_mate' in q.url else None)
            pg.on('response', lambda q: print('RES', q.url[-30:], q.text()[:300]) if 'giunto_asse' in q.url or 'add_mate' in q.url else None)
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = "async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json(); if (r.state) await window.__steelcad.apply(r); return r; }"
        r = pg.evaluate(api, ['new_assembly_con_pezzi', ['Cancello', [{'path': str(cart / 'PILASTRO.steelcad')}, {'path': str(cart / 'ANTA UFFICIO.steelcad')}]]])
        pg.evaluate("window.__steelcad.hideHome()")
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        # il pilastro a sinistra dell'anta, 2 mm di luce; l'anta al suo posto (0, 0, 0)
        pose = pg.evaluate("window.__steelcad.state.poses")
        t1, t2 = [pose['I1'][3], pose['I1'][7], pose['I1'][11]], [pose['I2'][3], pose['I2'][7], pose['I2'][11]]
        pg.evaluate(api, ['asm_move', ['I1', -82 - t1[0], -40 - t1[1], -t1[2]]])
        pg.evaluate(api, ['asm_move', ['I2', -t2[0], -t2[1], -t2[2]]])
        pg.evaluate("window.__prova.call('scene').then(() => 0)")
        time.sleep(1.0)
        pg.keyboard.press('Escape')
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
        pg.screenshot(path=str(out / 'mv1_assieme.png'))

        ok('gruppo «Movimento» nella barra con Cerniera, Guida, Perno',
           all(pg.evaluate(f"!!document.querySelector('[data-asm-tool=\"{k}\"]')") for k in ('cerniera', 'guida', 'perno')))
        comando(pg, '[data-asm-tool="cerniera"]')
        ok('suggerimento: l’asse', 'asse' in pg.inner_text('#sk-help'))

        def schermo(pt):
            x, y = pg.evaluate("(p) => window.__steelcad.toScreen(p)", pt)
            r = pg.evaluate("(() => { const r = document.querySelector('#c3d').getBoundingClientRect(); return [r.left, r.top]; })()")
            return x + r[0], y + r[1]

        # lo spigolo davanti a sinistra dell'anta (x 0, y −20), a metà altezza
        x, y = schermo([0, -20, 700])
        pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y)
        try:
            pg.wait_for_function("window.__giunti.asse", timeout=10000)
        except Exception:
            pg.screenshot(path=str(out / 'mv_errore.png'))
            print(pg.inner_text('body')[-600:], err)
            raise
        asse = pg.evaluate("window.__giunti.asse")
        print('     asse', asse)
        ok('primo clic: l’asse è lo spigolo, verticale', asse['cosa'] == 'lo spigolo' and abs(abs(asse['d'][2]) - 1) < 1e-6
           and abs(asse['p'][0]) < 5 and abs(asse['p'][1] + 20) < 5)
        time.sleep(0.3)
        pg.screenshot(path=str(out / 'mv2_asse.png'))
        x, y = schermo([-42, -40, 1500])            # la faccia davanti del pilastro
        pg.mouse.click(x, y)
        pg.wait_for_selector('.giunto-pan', timeout=15000)
        time.sleep(0.6)
        t = pg.inner_text('#props')
        ok('pannello del giunto: muovi, finecorsa, controlla', all(k in t for k in ('Gira di', 'Finecorsa', 'Trova da solo', 'Controlla che non sbatta', 'Torna com’era', 'Tieni questa posizione')))
        ok('nell’albero «ANTA UFFICIO in cerniera su PILASTRO»', 'in cerniera su' in json.dumps(pg.evaluate("window.__steelcad.state.tree"), ensure_ascii=False))
        pg.screenshot(path=str(out / 'mv3_pannello.png'))
        m0 = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        print('     anta', [round(v, 3) for v in m0[:12]])
        ok('creando la cerniera l’anta non si sposta', abs(m0[3]) < 1e-6 and abs(m0[0] - 1) < 1e-9)
        passi = len(pg.evaluate("window.__steelcad.state.storia.passi"))

        # a metà corsa: scrive 45, il pezzo si muove mentre scrive (prima di Invio)
        pg.fill('#g-angolo', '45')
        pg.wait_for_function("Math.abs(window.__steelcad.objs.get('I2').data.matrix[0] - Math.cos(Math.PI/4)) < 1e-6", timeout=10000)
        time.sleep(0.4)
        pg.screenshot(path=str(out / 'mv4_meta_corsa.png'))
        ok('anteprima mentre scrive: a 45° prima di Invio', True)
        pg.fill('#g-angolo', 'aperta 90')
        pg.press('#g-angolo', 'Enter')
        pg.wait_for_function("window.__steelcad.state.giunti[0].valori.angolo === 90", timeout=10000)
        time.sleep(0.6)
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('«aperta 90» e Invio: l’anta a 90°', abs(m[0]) < 1e-6)
        ok('«Torna com’era» e «Tieni» si accendono', not pg.is_disabled('#g-torna') and not pg.is_disabled('#g-tieni'))
        ok('il disegno non è cambiato (nessun passo in più nella storia)', len(pg.evaluate("window.__steelcad.state.storia.passi")) == passi)
        pg.screenshot(path=str(out / 'mv5_aperta.png'))

        # col mouse: trascina l'anta (è scelta col giunto): gira attorno allo spigolo
        prima = pg.evaluate("window.__steelcad.state.giunti[0].valori.angolo")
        p0 = pg.evaluate("""() => { const o = window.__steelcad.objs.get('I2'), T = window.__steelcad.THREE;
            return new T.Vector3(700, 0, 1100).applyMatrix4(o.mesh.matrixWorld).toArray(); }""")
        x, y = schermo(p0)
        pg.mouse.move(x, y); pg.mouse.down()
        for k in range(1, 13):
            pg.mouse.move(x + 14 * k, y + 3 * k); time.sleep(0.05)
        time.sleep(0.3)
        ok('mentre trascina: il cartellino col valore', 'Gira' in pg.inner_text('#hover-tip'))
        pg.screenshot(path=str(out / 'mv6_trascina.png'))
        pg.mouse.up()
        pg.wait_for_function(f"Math.abs(window.__steelcad.state.giunti[0].valori.angolo - {prima}) > 1", timeout=10000)
        time.sleep(0.5)
        dopo = pg.evaluate("window.__steelcad.state.giunti[0].valori.angolo")
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok(f'trascinata col mouse: da {prima}° a {round(dopo, 1)}°, sempre sull’asse', abs(dopo - prima) > 1
           and abs(m[11]) < 1e-6 and abs(m[10] - 1) < 1e-9)

        # Trova da solo
        pg.click('#g-trova')
        pg.wait_for_function("document.querySelector('#g-da-angolo') && document.querySelector('#g-da-angolo').value !== ''", timeout=60000)
        time.sleep(0.5)
        g = pg.evaluate("window.__steelcad.state.giunti[0]")
        lo, hi = g['limiti']['angolo']
        ok(f'«Trova da solo»: da {lo}° a {hi}°, ferma contro il pilastro', lo is not None and hi is not None and lo < 0 < hi
           and 'PILASTRO' in pg.inner_text('#g-trova-esito'))
        pg.screenshot(path=str(out / 'mv7_finecorsa.png'))

        # Controlla che non sbatta: il finecorsa scritto più largo del vero → tocca, punto rosso
        larga = round(hi + 15)
        pg.fill('#g-a-angolo', str(larga)); pg.press('#g-a-angolo', 'Enter')
        pg.wait_for_function(f"window.__steelcad.state.giunti[0].limiti.angolo[1] === {larga}", timeout=10000)
        time.sleep(0.4)
        pg.click('#g-controlla')
        pg.wait_for_function("window.__giunti.punti > 0", timeout=60000)
        time.sleep(0.6)
        es = pg.inner_text('#g-controlla-esito')
        ok(f'«Controlla»: sbatte contro il pilastro ({es[:60]}…)', 'Sbatte' in es and 'PILASTRO' in es)
        ok('il cartellino rosso «tocca»', pg.is_visible('.dim.interf:has-text("tocca")'))
        pg.screenshot(path=str(out / 'mv8_sbatte.png'))

        # Torna com'era
        pg.click('#g-torna')
        pg.wait_for_function("!window.__steelcad.state.giunti[0].mosso", timeout=10000)
        time.sleep(0.5)
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('«Torna com’era»: l’anta chiusa', abs(m[0] - 1) < 1e-9 and abs(m[3]) < 1e-6)
        # il pezzo scelto: «Si muove» col campo
        pg.evaluate("window.__steelcad.select('I2')"); time.sleep(0.8)
        ok('barretta del pezzo: «Gira 0°»', pg.is_visible('#mini-barra button[data-t^="Gira 0°"]'))
        pg.screenshot(path=str(out / 'mv9a_barretta.png'))
        pg.click('#mini-barra .piu'); pg.wait_for_selector('#a-nome', timeout=5000); time.sleep(0.4)
        ok('pannello del pezzo: «Si muove» col valore', 'Si muove' in pg.inner_text('#props') and pg.is_visible('#gi0-angolo'))
        pg.fill('#gi0-angolo', '30'); pg.press('#gi0-angolo', 'Enter')
        pg.wait_for_function("window.__steelcad.state.giunti[0].valori.angolo === 30", timeout=10000)
        time.sleep(0.5)
        pg.screenshot(path=str(out / 'mv9_pezzo.png'))
        pg.evaluate("window.__prova.applyTheme(true)"); time.sleep(0.5)
        pg.evaluate("window.__steelcad.select('mate=M1')"); time.sleep(0.8)
        pg.screenshot(path=str(out / 'mv10_scuro.png'))
        pg.evaluate("window.__prova.applyTheme(false)")
        ok('nessun errore nella pagina', not err)
        if err:
            print(err[:3])
        b.close()
finally:
    srv.kill()
    shutil.rmtree(tmp, ignore_errors=True)
print(f'{sum(esiti)}/{len(esiti)} ok · screenshot in {out}')
sys.exit(0 if all(esiti) else 1)
