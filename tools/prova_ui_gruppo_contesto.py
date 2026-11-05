"""Prova dell'interfaccia (05/11): «Blocca insieme» e il pezzo modificato dentro l'assieme, nel browser senza finestra.

Piastra + due staffe. «Blocca insieme», clic sulle due staffe, «Blocca insieme (2)»: nell'albero il gruppo con i due
pezzi; «Appoggia» la prima staffa sulla piastra: nell'anteprima e dopo si muove anche la seconda, come stavano.
Poi «Apri il pezzo» sulla prima staffa: gli altri pezzi attorno in trasparenza; sketch sulla sua faccia e «Vedi
attraverso»: anche i bordi della piastra e dell'altra staffa, per agganciarsi. «Torna all'assieme». Foto nella cartella.

    python tools/prova_ui_gruppo_contesto.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright
from ui_barra import comando

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5322
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


CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
        aggiorna = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); return r; }")

        def pezzo(*a):
            assert pg.evaluate(api, list(a))['ok']
            assert pg.evaluate(api, ['save', [True]])['ok']
        pezzo('new_project', ['lamiera', {'name': 'Piastra', 'larghezza': 400, 'profondita': 300, 'spessore': 8}])
        pezzo('crea_da_modello', ['staffa', {'nome': 'Staffa', 'larghezza': 100, 'profondita': 80, 'altezza': 80, 'spessore': 3,
                                             'raggio': 3, 'k': 0.33}])
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                        ['Staffe', [{'path': str(cart / 'Piastra.steelcad')}, {'path': str(cart / 'Staffa.steelcad'), 'n': 2}]])
        pg.wait_for_function("window.__steelcad.objs.size === 3", timeout=20000)
        pg.evaluate(aggiorna, ['asm_rotate', ['I3', 'z', 90]])
        pg.evaluate(aggiorna, ['asm_move', ['I3', 0, 160, 0]])
        assert pg.evaluate(aggiorna, ['save', [str(cart / 'Staffe.steelcad-asm')]])['ok']
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(1.0)
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")

        def centro(iid):
            return pg.evaluate("""(iid) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const b = new T.Box3().setFromObject(o.mesh), c = b.getCenter(new T.Vector3());
                const q = c.project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", iid)

        def schermo(iid, nome):
            return pg.evaluate("""([iid, nome]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const f = o.data.faces.find(f => f.name === nome); const pos = o.data.positions, idx = o.data.indices;
                const c = new T.Vector3(); let n = 0;
                for (let k = f.start; k < f.start + f.count; k++) { c.add(new T.Vector3(pos[idx[k]*3], pos[idx[k]*3+1], pos[idx[k]*3+2])); n++; }
                c.multiplyScalar(1 / n); c.applyMatrix4(o.mesh.matrixWorld);
                const q = c.clone().project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, nome])

        def clic(x, y):
            pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.4)

        # ---------------------------------------------------------------- 1. Blocca insieme
        ok('pulsante «Blocca insieme» nella barra dell’assieme', pg.is_visible('[data-asm-tool="gruppo"]:has-text("Blocca insieme")'))
        comando(pg, '[data-asm-tool="gruppo"]')
        pg.wait_for_selector('#gruppo-pan', timeout=5000)
        ok('pannello «Blocca insieme», pulsante spento finché non ci sono due pezzi', pg.is_disabled('#gr-ok'))
        clic(*schermo('I2', 'SM1/sopra')); clic(*schermo('I3', 'SM1/sopra'))
        t = pg.inner_text('#gruppo-pan')
        ok('scelte le due staffe (Invio blocca)', not pg.is_disabled('#gr-ok') and t.count('Staffa') >= 2
           and 'Invio blocca' in (pg.get_attribute('#sk-help', 'title') or ''))
        pg.screenshot(path=str(out / 'g1_scelti.png'))
        pg.evaluate("window.__prova.applyTheme(true)"); time.sleep(0.4)
        pg.screenshot(path=str(out / 'g1b_scelti_scuro.png'))
        pg.evaluate("window.__prova.applyTheme(false)"); time.sleep(0.3)
        pg.click('#gr-ok')
        pg.wait_for_function("window.__steelcad.state.tree.children.some(c => c.kind === 'rigido')", timeout=15000)
        time.sleep(0.8)
        st = pg.evaluate('window.__steelcad.state')
        g = next(c for c in st['tree']['children'] if c['kind'] == 'rigido')
        ok(f'nell’albero «{g["label"]}» con i due pezzi', [c['ref'] for c in g['children']] == ['I2', 'I3'])
        ok('la distinta: sempre 2 staffe e 1 piastra', sorted(r['qty'] for r in st['bom']) == [1, 2])
        ok('il gruppo nell’albero si vede', pg.is_visible('#tree .node[data-kind="rigido"]'))
        pg.screenshot(path=str(out / 'g2_gruppo_albero.png'))
        pg.click('#tree .node[data-kind="rigido"]'); time.sleep(0.8)
        pg.evaluate("window.__steelcad.select('I3')"); time.sleep(1.0)
        clic(*schermo('I3', 'SM1/sopra')); time.sleep(0.8)
        pg.click('#mini-barra .piu'); time.sleep(1.0)              # «⋯»: il pannello intero del pezzo
        pan = pg.evaluate("document.body.innerText")
        ok('pannello del pezzo: «Bloccato insieme» e «Sciogli il gruppo»', 'Bloccato insieme' in pan and 'Sciogli il gruppo' in pan)
        pg.screenshot(path=str(out / 'g2b_pannello_pezzo.png'))
        pg.keyboard.press('Escape'); time.sleep(0.4)

        def rel():
            ist = {i['id']: i for i in pg.evaluate(api, ['state', []]).get('instances', [])}
            d = pg.evaluate("window.__steelcad.state.poses")
            A, B = np.array(d['I2']).reshape(4, 4), np.array(d['I3']).reshape(4, 4)
            return np.linalg.inv(A) @ B, ist
        prima, _ = rel()

        # ---------------------------------------------------------------- 2. Appoggia porta tutto il gruppo
        comando(pg, '[data-asm-tool="appoggia"]')
        clic(*schermo('I2', 'SM1/sopra'))
        clic(*schermo('I1', 'SM1/sopra'))
        pg.wait_for_selector('#appoggia .ap-dove', timeout=15000); time.sleep(0.8)
        anteprima = pg.evaluate("""() => { const S = window.__steelcad; return ['I2', 'I3'].map(id => [...S.objs.get(id).mesh.matrixWorld.elements]); }""")
        pg.screenshot(path=str(out / 'g3_appoggia_anteprima.png'))
        pg.click('#ap-ok')
        pg.wait_for_function("!document.querySelector('#appoggia')", timeout=15000); time.sleep(1.0)
        dopo, _ = rel()
        ok('dopo Appoggia le due staffe stanno come prima tra loro', np.allclose(prima, dopo, atol=1e-4))
        d = pg.evaluate("window.__steelcad.state.poses")
        ok('l’anteprima muoveva anche la seconda staffa (dove poi è andata)',
           np.allclose(np.array(anteprima[1]).reshape(4, 4).T[:3, 3], np.array(d['I3']).reshape(4, 4)[:3, 3], atol=1e-3))
        ok('nessun avviso', not pg.evaluate("window.__steelcad.state.warnings"))
        pg.screenshot(path=str(out / 'g4_appoggiate.png'))

        # ---------------------------------------------------------------- 3. il pezzo dentro l'assieme
        pg.evaluate("window.__prova.apriPezzoAssieme('I2')")
        pg.wait_for_function("window.__steelcad.state.mode !== 'assembly' && window.__steelcad.state.can_back", timeout=20000)
        time.sleep(1.2)
        sc = pg.evaluate(api, ['scene', []])
        ctx = [o for o in sc.get('objects', []) if o.get('kind') == 'context']
        ok(f'aperta la staffa: gli altri {len(ctx)} pezzi attorno, non cliccabili', len(ctx) == 2)
        pg.screenshot(path=str(out / 'g5_pezzo_nel_contesto.png'))
        r = pg.evaluate(aggiorna, ['sketch_on_face', ['SM1/sopra']])
        ok('sketch sulla faccia della staffa', r.get('ok'))
        pg.evaluate("(sid) => window.__steelcad.enterSketch(sid)", r['sketch']); time.sleep(1.2)
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")
        pg.keyboard.press('v'); time.sleep(2.0)
        toast = pg.evaluate("[...document.querySelectorAll('.toast')].map(t => t.innerText).join(' | ')")
        ok(f'«Vedi attraverso»: anche i bordi dei pezzi attorno ({toast[:90]}…)', 'pezzi attorno' in toast)
        v = pg.evaluate('window.__steelcad.sketch.v')
        xs = [q['xy'][0] for q in v['points'] if q['id'] != 'O']
        ok(f'nello sketch c’è il bordo della piastra (largo {max(xs) - min(xs):.0f} mm, la staffa 100)', max(xs) - min(xs) > 390)
        pg.evaluate("window.__steelcad.runCmd('fit')"); time.sleep(1.2)
        pg.screenshot(path=str(out / 'g6_sketch_vede_attorno.png'))
        pg.keyboard.press('v'); time.sleep(1.0)
        pg.evaluate("window.__steelcad.exitSketch()"); time.sleep(0.8)
        pg.click('#b-back')
        pg.wait_for_function("window.__steelcad.state.mode === 'assembly'", timeout=20000); time.sleep(1.2)
        st = pg.evaluate('window.__steelcad.state')
        ok('tornati all’assieme col gruppo', any(c['kind'] == 'rigido' for c in st['tree']['children']))
        fin, _ = rel()
        ok('le staffe sempre insieme', np.allclose(prima, fin, atol=1e-4))
        pg.screenshot(path=str(out / 'g7_assieme_di_nuovo.png'))

        # ---------------------------------------------------------------- 4. Sciogli
        pg.click('#tree .node[data-kind="rigido"]', button='right'); time.sleep(0.4)
        ok('tasto destro sul gruppo: «Sciogli il gruppo»', pg.is_visible('#menu-albero button[data-v="sciogli"]'))
        pg.click('#menu-albero button[data-v="sciogli"]')
        pg.wait_for_function("!window.__steelcad.state.tree.children.some(c => c.kind === 'rigido')", timeout=15000)
        ok('sciolto: nell’albero di nuovo i pezzi uno per uno', True)
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
