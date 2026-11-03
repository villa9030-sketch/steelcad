"""Prova dell'interfaccia di «Appoggia» (03/11) nel browser senza finestra: piastra 300×200 sp. 8 e staffa a L
100×80 h 80 sp. 3; «Appoggia», clic sulla faccia della staffa che si vede, clic sulla piastra → staffa sopra, al
centro, dritta; poi su un bordo e a misura, Fatto. Screenshot nella cartella data.

    python tools/prova_ui_appoggia.py [cartella_screenshot] [porta]
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
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5261
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
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
        api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
        assert pg.evaluate(api, ['new_project', ['lamiera', {'name': 'Piastra base', 'larghezza': 300, 'profondita': 200, 'spessore': 8}]])['ok']
        assert pg.evaluate(api, ['save', [True]])['ok']
        assert pg.evaluate(api, ['crea_da_modello', ['staffa', {'nome': 'Staffa a L', 'larghezza': 100, 'profondita': 80, 'altezza': 80, 'spessore': 3,
                                                                'raggio': 3, 'k': 0.33}]])['ok']
        assert pg.evaluate(api, ['save', [True]])['ok']
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                        ['Piastra con staffa', [{'path': str(cart / 'Piastra base.steelcad')}, {'path': str(cart / 'Staffa a L.steelcad')}]])
        print("assieme", r, pg.evaluate("[window.__steelcad.state.mode, window.__steelcad.objs.size]"), err)
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'ap1_assieme.png'))

        def schermo(iid, nome):
            return pg.evaluate("""([iid, nome]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const f = o.data.faces.find(f => f.name === nome); const pos = o.data.positions, idx = o.data.indices;
                const c = new T.Vector3(); let n = 0;
                for (let k = f.start; k < f.start + f.count; k++) { c.add(new T.Vector3(pos[idx[k]*3], pos[idx[k]*3+1], pos[idx[k]*3+2])); n++; }
                c.multiplyScalar(1 / n); c.applyMatrix4(o.mesh.matrixWorld);
                const q = c.clone().project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, nome])

        ok('pulsante «Appoggia» con il nome nella barra', pg.is_visible('[data-asm-tool="appoggia"]:has-text("Appoggia")'))
        pg.click('[data-asm-tool="appoggia"]')
        ok('suggerimento: faccia del pezzo da mettere', 'pezzo da mettere' in pg.inner_text('#sk-help'))
        x, y = schermo('I2', 'SM1/sopra')
        pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.4)
        ok('poi chiede il pezzo fermo («sulla faccia», non «su la»)', 'sulla faccia del pezzo fermo' in pg.inner_text('#sk-help'))
        pg.screenshot(path=str(out / 'ap2_primo_clic.png'))
        x, y = schermo('I1', 'SM1/sopra')
        pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y)
        pg.wait_for_selector('#appoggia .ap-dove', timeout=15000)
        time.sleep(0.6)
        testo = pg.inner_text('#appoggia')
        ok('pannello: al centro, distanze dai bordi 100/100 e 60/60', 'sinistra 100' in testo and 'destra 100' in testo
           and 'davanti 60' in testo and 'dietro 60' in testo)
        pg.screenshot(path=str(out / 'ap3_anteprima_centro.png'))
        pg.click('#appoggia [data-dove="bordo"]')
        pg.wait_for_function("document.querySelector('#appoggia .ap-dist').textContent.includes('davanti 0')", timeout=10000)
        ok('su un bordo: contro il bordo davanti', True)
        pg.screenshot(path=str(out / 'ap4_su_un_bordo.png'))
        pg.click('#appoggia [data-dove="misura"]')
        pg.click('#appoggia [data-k="u"][data-modo="basso"]')
        pg.fill('#appoggia [data-mm="u"]', '20')
        pg.click('#appoggia [data-k="v"][data-modo="alto"]')
        pg.fill('#appoggia [data-mm="v"]', '30')
        pg.wait_for_function("document.querySelector('#appoggia .ap-dist').textContent.includes('sinistra 20')"
                             " && document.querySelector('#appoggia .ap-dist').textContent.includes('dietro 30')", timeout=10000)
        ok('a misura: 20 da sinistra, 30 da dietro (anteprima)', True)
        pg.screenshot(path=str(out / 'ap5_a_misura.png'))
        pg.click('#ap-ok')
        pg.wait_for_function("!document.querySelector('#appoggia') && window.__steelcad.state.tree.children.some(c => c.label === 'Accoppiamenti')",
                             timeout=15000)
        time.sleep(0.8)
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('Fatto: staffa a x 20, y 90 (dietro 30), z 8, dritta', abs(m[3] - 20) < 1e-6 and abs(m[7] - 90) < 1e-6 and abs(m[11] - 8) < 1e-6
           and abs(m[0] - 1) < 1e-9 and abs(m[10] - 1) < 1e-9)
        pg.screenshot(path=str(out / 'ap6_fatto.png'))
        # di nuovo, e Annulla: torna dov'era
        pg.click('[data-asm-tool="appoggia"]')
        x, y = schermo('I2', 'SM1/sopra'); pg.mouse.click(x, y); time.sleep(0.3)
        x, y = schermo('I1', 'SM1/sopra'); pg.mouse.click(x, y)
        pg.wait_for_selector('#appoggia .ap-dove', timeout=15000); time.sleep(0.4)
        pg.keyboard.press('Escape'); time.sleep(0.4)
        m2 = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('Esc: il pannello si chiude e la staffa torna dov’era', not pg.query_selector('#appoggia') and m2 == m)
        # la barretta del pezzo: icone con il nome, Apri / Appoggia / Sposta fuori da «⋯»
        x, y = schermo('I2', 'SM1/FL1/esterno'); pg.mouse.click(x, y)
        pg.wait_for_selector('#mini-barra.con-nomi', timeout=10000); time.sleep(0.5)
        nomi = pg.inner_text('#mini-barra')
        ok('barretta con i nomi: Apri il pezzo, Appoggia, Sposta, Pezzo nuovo qui', all(t in nomi for t in ('Apri il pezzo', 'Appoggia', 'Sposta', 'Pezzo nuovo qui')))
        pg.screenshot(path=str(out / 'ap7_barretta_con_nomi.png'))
        pg.click('#mini-barra button[data-t="Sposta"]')
        pg.wait_for_selector('#a-px', timeout=10000); time.sleep(0.5)
        dove = pg.evaluate("[...document.querySelectorAll('#props .xyz input')].map(i => i.value)")
        ok('Sposta dice dove sta: X 20 Y 90 Z 8, dai bordi 20/180/90/30', dove[:3] == ['20', '90', '8'] and dove[3:7] == ['20', '180', '90', '30'])
        pg.screenshot(path=str(out / 'ap8_sposta_dove_sta.png'))
        pg.keyboard.press('Escape'); time.sleep(0.3)
        # il nome del pezzo: doppio clic nell'elenco, scrivo, Invio → elenco, distinta, file
        pg.dblclick('#tree .node[data-kind="instance"][data-ref="I2"]')
        pg.wait_for_selector('#tree input.nome-albero', timeout=5000)
        pg.screenshot(path=str(out / 'ap9_rinomina.png'))
        pg.fill('#tree input.nome-albero', 'Staffa motore'); pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.instances.some(i => i.name === 'Staffa motore')", timeout=15000)
        time.sleep(0.5)
        ok('rinominato: elenco e distinta «Staffa motore»', 'Staffa motore' in pg.inner_text('#tree')
           and any(b['description'].startswith('Staffa motore') for b in pg.evaluate('window.__steelcad.state.bom')))
        pg.screenshot(path=str(out / 'ap10_rinominato.png'))
        ok('nessun errore JavaScript', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.terminate()
print(f'{sum(esiti)}/{len(esiti)} ok; screenshot in {out}')
sys.exit(0 if all(esiti) else 1)
