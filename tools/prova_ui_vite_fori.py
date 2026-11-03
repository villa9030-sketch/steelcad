"""Prova dell'interfaccia di «Vite nei fori» (03/11, secondo giro): base 300×200 sp. 8 con 4 fori Ø13 e un piatto
sp. 5 con fori Ø13; «Foro su foro», clic nel foro della base, clic nel foro del piatto → pannello con la vite già
proposta (M12 × 30 + dado), Invio → piatto sulla base, vite e dado al loro posto. Screenshot nella cartella data.

    python tools/prova_ui_vite_fori.py [cartella_screenshot] [porta]
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

        def piastra(nome, L, P, sp, fori, d):
            r0 = pg.evaluate(api, ['new_project', ['zero', {'name': nome}]])
            sid = next(c['ref'] for c in r0['state']['tree']['children'] if c['kind'] == 'sketch')
            assert pg.evaluate(api, ['sketch_add_rectangle', [sid, [0, 0], [L, P]]])['ok']
            for x, y in fori:
                assert pg.evaluate(api, ['sketch_add_circle', [sid, [x, y], d / 2]])['ok']
            assert pg.evaluate(api, ['create_from_sketch', [sid, 'plate', {'thickness': sp}]])['ok']
            assert pg.evaluate(api, ['save', [True]])['ok']
        piastra('Base', 300, 200, 8, [(25, 25), (275, 25), (275, 175), (25, 175)], 13)
        piastra('Piatto', 80, 60, 5, [(20, 30), (60, 30)], 13)
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                        ['Base e piatto', [{'path': str(cart / f'{n}.steelcad')} for n in ('Base', 'Piatto')]])
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'f1_assieme.png'))

        def vicino_al_foro(iid, x, y, z):
            """Il punto a schermo sulla faccia attorno al foro (x, y nel pezzo), 3 mm fuori dal bordo verso chi guarda:
            come clicca uno che non mira la parete del foro (piccola)."""
            return pg.evaluate("""([iid, p]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const v = new T.Vector3(...p).applyMatrix4(o.mesh.matrixWorld), q = v.project(S.camera);
                const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, [x, y - 6.5 - 3, z]])

        # vista dall'alto un po' girata per vedere le pareti dei fori: Iso va bene, avvicino
        comando(pg, '[data-asm-tool="asse"]')
        fa = vicino_al_foro('I1', 25, 25, 8)
        fb = vicino_al_foro('I2', 20, 30, 5)
        pg.mouse.move(*fa); time.sleep(0.2); pg.mouse.click(*fa); time.sleep(0.4)
        pg.screenshot(path=str(out / 'f1b_primo_clic.png'))
        ok('suggerimento: poi ti propongo la vite', 'propongo la vite' in pg.inner_text('#sk-help'))
        pg.mouse.move(*fb); time.sleep(0.2); pg.mouse.click(*fb)
        try:
            pg.wait_for_selector('#vitefori', timeout=15000); time.sleep(0.5)
        except Exception:
            pg.screenshot(path=str(out / 'f2_errore.png'))
            print('ERRORI', err, pg.evaluate("[...document.querySelectorAll('.toast, #toast')].map(e => e.textContent)"))
            raise
        t = pg.inner_text('#vitefori')
        print('   pannello:', t.replace('\n', ' | '))
        ok('2 clic: proposta M12 × 30 con dado (foro Ø13, pacco 13)', pg.input_value('#vf-m') == 'M12' and pg.input_value('#vf-l') == '30'
           and pg.is_checked('#vf-d') and 'Ø13' in t)
        pg.screenshot(path=str(out / 'f2_proposta.png'))
        pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.objs.size === 4", timeout=30000)
        time.sleep(1.0)
        pg.click('text=Inquadra'); time.sleep(0.6)
        pg.screenshot(path=str(out / 'f3_vite_messa.png'))
        st = pg.evaluate("window.__steelcad.state")
        nomi = [i['name'] for i in st['instances']]
        ok('Invio: vite TE M12x30 e dado M12 nell’assieme', any('TE M12x30' in n for n in nomi) and any('Dado M12' in n for n in nomi))
        ok('niente avvisi di accoppiamenti in contrasto', not st.get('warnings'))
        ok('nessuna interferenza', 'Nessuna' in pg.evaluate(api, ['asm_interferences', []])['message'])
        # il secondo foro del piatto: altri 2 clic (lo strumento resta attivo) e Invio
        fa = vicino_al_foro('I1', 275, 25, 8)
        pg.mouse.click(*vicino_al_foro('I2', 60, 30, 5)); time.sleep(0.4)
        ok('foro su foro resta attivo', pg.evaluate("document.querySelector('[data-asm-tool=\"asse\"]').classList.contains('on')"))
        ok('nessun errore JavaScript', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.terminate()
print(f'{sum(esiti)}/{len(esiti)} ok; screenshot in {out}')
sys.exit(0 if all(esiti) else 1)
