"""Prova dell'interfaccia di «Appoggia», secondo giro (03/11): una piastra più grande del fondo di una vaschetta si
posa sui bordi (non entra), una piastra lunga messa di traverso si gira da sola per stare nel fondo, una staffa nel
fondo resta al centro (le pieghe non hanno lati piani: tiene lo stesso), «Faccia su faccia» con la faccia che guarda
dalla stessa parte non fa entrare la staffa. Screenshot nella cartella data.

    python tools/prova_ui_appoggia_vaschetta.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando, comando_visibile  # noqa: F401  (comandi della barra, anche in «Altro ▾»)

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5267
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
        aggiorna = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); return r; }")

        def pezzo(*a):
            assert pg.evaluate(api, list(a))['ok']
            assert pg.evaluate(api, ['save', [True]])['ok']
        pezzo('crea_da_modello', ['scatola', {'nome': 'Vaschetta', 'larghezza': 200, 'profondita': 150, 'altezza': 50,
                                              'spessore': 2, 'raggio': 2, 'k': 0.33}])
        pezzo('new_project', ['lamiera', {'name': 'Piastra', 'larghezza': 300, 'profondita': 200, 'spessore': 8}])
        pezzo('new_project', ['lamiera', {'name': 'Lunga', 'larghezza': 180, 'profondita': 100, 'spessore': 5}])
        pezzo('crea_da_modello', ['staffa', {'nome': 'Staffa', 'larghezza': 100, 'profondita': 80, 'altezza': 80, 'spessore': 3,
                                             'raggio': 3, 'k': 0.33}])
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                        ['Vaschetta e piastre', [{'path': str(cart / f'{n}.steelcad')} for n in ('Vaschetta', 'Piastra', 'Lunga', 'Staffa')]])
        pg.wait_for_function("window.__steelcad.objs.size === 4", timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'v1_assieme.png'))

        def schermo(iid, nome):
            return pg.evaluate("""([iid, nome]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const f = o.data.faces.find(f => f.name === nome); const pos = o.data.positions, idx = o.data.indices;
                const c = new T.Vector3(); let n = 0;
                for (let k = f.start; k < f.start + f.count; k++) { c.add(new T.Vector3(pos[idx[k]*3], pos[idx[k]*3+1], pos[idx[k]*3+2])); n++; }
                c.multiplyScalar(1 / n); c.applyMatrix4(o.mesh.matrixWorld);
                const q = c.clone().project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, nome])

        def appoggia(mob, fer, nome):
            comando(pg, '[data-asm-tool="appoggia"]')
            x, y = schermo(*mob); pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.4)
            x, y = schermo(*fer); pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y)
            pg.wait_for_selector('#appoggia .ap-dove', timeout=15000)
            time.sleep(0.8)
            pg.screenshot(path=str(out / f'{nome}_anteprima.png'))
            t = pg.inner_text('#appoggia')
            pg.click('#ap-ok')
            pg.wait_for_function("!document.querySelector('#appoggia')", timeout=15000)
            time.sleep(1.0)
            pg.screenshot(path=str(out / f'{nome}_fatto.png'))
            return t

        def interf():
            return pg.evaluate(api, ['asm_interferences', []])['message']

        def nascondi(iid, n):
            pg.evaluate(aggiorna, ['asm_remove', [iid]])
            pg.wait_for_function(f"window.__steelcad.objs.size === {n}", timeout=20000)
            time.sleep(0.6)

        # 1. la piastra grande sul fondo (si vede la faccia di sopra del fondo, dentro la vaschetta)
        t = appoggia(('I2', 'SM1/sopra'), ('I1', 'SM1/sopra'), 'v2_piastra_sul_fondo')
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        print('   pannello piastra:', t.replace('\n', ' | '))
        ok('piastra grande: posata sui bordi (z 50), al centro, e lo dice', 'non ci sta' in t and abs(m[11] - 50) < 1e-6
           and abs(m[3] + 50) < 1e-6 and abs(m[7] + 25) < 1e-6)
        ok('nessuna interferenza', 'Nessuna' in interf())
        nascondi('I2', 3)
        # 2. la piastra lunga girata di traverso: nel fondo ci sta solo per il lungo, la gira da sola
        pg.evaluate(aggiorna, ['asm_rotate', ['I3', 'z', 90]])
        time.sleep(0.8)
        t = appoggia(('I3', 'SM1/sopra'), ('I1', 'SM1/sopra'), 'v3_lunga_girata')
        m = pg.evaluate("window.__steelcad.objs.get('I3').data.matrix")
        print('   pannello lunga:', t.replace('\n', ' | '))
        ok('lunga: dentro il fondo (z 2), nessuna interferenza', abs(m[11] - 2) < 1e-6 and 'Nessuna' in interf())
        nascondi('I3', 2)
        # 3. la staffa nel fondo: al centro e tiene (nessun avviso «non c'è un lato piano»)
        t = appoggia(('I4', 'SM1/sopra'), ('I1', 'SM1/sopra'), 'v4_staffa_nel_fondo')
        print('   pannello staffa:', t.replace('\n', ' | '))
        ok('staffa nel fondo: al centro, senza avviso di lato piano', 'lato piano' not in t and 'sinistra 46' in t)
        # 4. Faccia su faccia: la staffa tolta dagli accoppiamenti e rimessa cliccando la faccia che si vede
        msg = pg.evaluate(aggiorna, ['asm_add_mate', ['faccia', {'inst': 'I1', 'face': pg.evaluate(
            "window.__steelcad.objs.get('I1').data.faces.find(f => f.name === 'SM1/sotto').index")},
            {'inst': 'I4', 'face': pg.evaluate("window.__steelcad.objs.get('I4').data.faces.find(f => f.name === 'SM1/sotto').index")}, 0, False, None, None, True]])
        time.sleep(0.8)
        m = pg.evaluate("window.__steelcad.objs.get('I4').data.matrix")
        pg.screenshot(path=str(out / 'v5_faccia_su_faccia_sotto.png'))
        ok('faccia su faccia sotto/sotto: la staffa va sotto la vaschetta senza capovolgersi', msg['ok'] and abs(m[10] + 1) > 1e-6 and m[11] < 0)
        ok('nessun errore JavaScript', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.terminate()
print(f'{sum(esiti)}/{len(esiti)} ok; screenshot in {out}')
sys.exit(0 if all(esiti) else 1)
