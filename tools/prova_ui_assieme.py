"""Prova dell'interfaccia degli assiemi in Chrome: nuovo assieme, pezzi, faccia su faccia col mouse, pannelli,
apri il pezzo e torna, interferenze, distinta.

    python tools/prova_ui_assieme.py [cartella_screenshot] --chrome
"""
import subprocess, sys, tempfile, time, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]; PY = ROOT / '.venv' / 'Scripts' / 'python.exe'; PORTA = 5130
out = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else Path(tempfile.mkdtemp())
out.mkdir(parents=True, exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000)
while not srv.stdout.readline().startswith(b'http'):    # il server è pronto
    pass
esiti = []
def ok(t, c): esiti.append(bool(c)); print(('OK   ' if c else 'NO   ') + t, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
        # i due pezzi: piastra con due fori, staffa a L con due fori
        for nome, L, P, sp, fori, fl in (('piastra', 200, 100, 3, [[60, 50], [140, 50]], None), ('staffa', 100, 40, 2, [[10, 20], [90, 20]], 'L3')):
            pg.evaluate(api, ['new_project', ['lamiera', {'name': nome, 'larghezza': L, 'profondita': P, 'spessore': sp, 'raggio': 2, 'k': 0.4}]])
            sid = pg.evaluate(api, ['sketch_on_face', ['SM1/sopra']])['sketch']
            for c in fori:
                pg.evaluate(api, ['sketch_add_circle', [sid, c, 4]])
            pg.evaluate(api, ['create_from_sketch', [sid, 'cut', {}]])
            if fl:
                pg.evaluate(api, ['add_flange', ['SM1', fl, {'length': '50'}]])
            assert pg.evaluate(api, ['save', [True]])['ok']
        pg.evaluate(api, ['new_project', ['zero', {'name': 'vuoto'}]])
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        pg.click('#top .brand'); pg.wait_for_selector('#home:not([hidden])')
        pg.click('#home [data-new="assieme"]'); pg.fill('#n-name', 'Prova assieme'); pg.click('#n-ok')
        pg.wait_for_function("window.__steelcad.state.mode === 'assembly'")
        try:  # la pagina iniziale si chiude quando l'assieme ha finito di caricarsi (subito dopo lo stato)
            pg.wait_for_function("document.querySelector('#home').hidden", timeout=10000)
        except Exception:
            pass
        ok('pagina iniziale → nuovo assieme', pg.evaluate("document.querySelector('#home').hidden"))
        ok('scheda ASSIEME e niente Parametri', pg.is_visible('.rtabs [data-rtab="assieme"]') and not pg.is_visible('#params'))
        for f in ('piastra', 'staffa'):
            pg.evaluate("async (p) => { const r = await (await fetch('/api/asm_insert', {method: 'POST', body: JSON.stringify([p])})).json(); await window.__steelcad.apply(r); }", str(cart / (f + '.steelcad')))
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=15000); time.sleep(0.8)
        ok('due pezzi nella scena', True)
        pg.screenshot(path=str(out / '1_inseriti.png'))
        # faccia su faccia col mouse: sopra della piastra, sotto della staffa
        def schermo(iid, nome, verso):
            return pg.evaluate("""([iid, nome, verso]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const fs = o.data.faces.filter(f => f.name === nome); let best = null;
                for (const f of fs) { const pos = o.data.positions, idx = o.data.indices; const c = new T.Vector3(); let n = 0;
                  for (let k = f.start; k < f.start + f.count; k++) { c.add(new T.Vector3(pos[idx[k]*3], pos[idx[k]*3+1], pos[idx[k]*3+2])); n++; }
                  c.multiplyScalar(1 / n); if (!best) best = c; }
                best.applyMatrix4(o.mesh.matrixWorld);
                const q = best.clone().project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, nome, verso])
        pg.click('[data-asm-tool="faccia"]')
        x, y = schermo('I1', 'SM1/sopra', 1); pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.5)
        ok('primo clic: chiede la faccia dell’altro pezzo', 'altro pezzo' in pg.inner_text('#sk-help'))
        # la faccia di sotto della staffa: giro la vista da sotto? basta la faccia sopra della staffa (allinea poi con Inverti)
        x, y = schermo('I2', 'SM1/sopra', 1); pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y)
        pg.wait_for_function("window.__steelcad.state.tree.children.some(c => c.label === 'Accoppiamenti')", timeout=15000)
        ok('faccia su faccia creato col mouse', True)
        pg.keyboard.press('Escape')
        time.sleep(0.8)
        pg.screenshot(path=str(out / '2_accoppiati.png'))
        # pannello accoppiamento: distanza
        pg.click('#tree .node:has-text("M1")')
        pg.wait_for_selector('#m-off'); pg.fill('#m-off', '10'); pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.tree.children.find(c => c.label === 'Accoppiamenti').children[0].label.includes('distanza 10')", timeout=15000)
        ok('distanza 10 dal pannello dell’accoppiamento', True)
        # la radice dell'albero: ruota tutto l'assieme insieme
        pg.click('#tree .node.root, #tree > ul > li > .node')
        pg.wait_for_selector('[data-rotall="z"]')
        prima = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.matrix.map(x => x.toFixed(2)).join()).join('|')")
        pg.click('[data-rotall="z"]'); pg.wait_for_timeout(1500)
        dopo = pg.evaluate("[...window.__steelcad.objs.values()].map(o => o.data.matrix.map(x => x.toFixed(2)).join()).join('|')")
        ok('radice dell’assieme: ruota tutto (Z 90°)', prima != dopo and not pg.inner_text('#toasts').strip().lower().count('errore'))
        pg.keyboard.press('Control+z'); pg.wait_for_timeout(1000)
        # pannello istanza: ruota, apri pezzo e torna
        pg.click('#tree .node:has-text("staffa")')
        pg.wait_for_selector('#a-open')
        ok('pannello istanza con Sposta/Ruota/Apri', pg.is_visible('[data-rot="z"]'))
        pg.click('#a-open'); pg.wait_for_function("window.__steelcad.state.mode === 'part' && window.__steelcad.state.can_back", timeout=15000)
        ok('Apri il pezzo → si lavora sul pezzo, c’è “← Assieme”', pg.is_visible('#b-back'))
        pg.click('#b-back'); pg.wait_for_function("window.__steelcad.state.mode === 'assembly'", timeout=15000)
        try:
            pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=10000)
        except Exception:
            pass
        ok('← Assieme: di nuovo nell’assieme', pg.evaluate("window.__steelcad.objs.size") == 2)
        pg.click('[data-cmd="asm_interf"]'); time.sleep(1.5)
        ok('controllo interferenze risponde: ' + pg.inner_text('#toasts')[-80:].replace('\n', ' '), 'interferenz' in pg.inner_text('#toasts').lower())
        pg.click('.tabs button[data-tab="bom"]')
        ok('distinta dell’assieme: ' + pg.inner_text('#tab-bom')[:90].replace('\n', ' '), 'piastra' in pg.inner_text('#tab-bom').lower() and 'staffa' in pg.inner_text('#tab-bom').lower())
        pg.screenshot(path=str(out / '3_fine.png'))
        ok('nessun errore in pagina', not err)
        for e in err: print('  ', e)
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
