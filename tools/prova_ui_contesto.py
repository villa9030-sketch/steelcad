"""Prova dell'interfaccia: pezzo nuovo disegnato nell'assieme (nel contesto), cliccando come l'utente.

    python tools/prova_ui_contesto.py [cartella]        (Python con Playwright; Chromium senza finestra)

Due piastre nell'assieme; clic sulla faccia di sopra della prima, «Nuovo pezzo su questa faccia», rettangolo da
una piastra all'altra agganciato ai bordi arancio, «Crea lamiera», «← Assieme»: la lamiera è montata sopra le due.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

QUI = Path(__file__).resolve().parents[1]
CART = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
SHOTS = CART / 'shots'; SHOTS.mkdir(parents=True, exist_ok=True)
(CART / 'r.json').write_text('{"format": "steelcad-regole", "rules": [], "default": {"radius": 1, "method": "k", "k": 0.21}}', encoding='utf-8')
risultati = []


def ok(cosa, esito):
    risultati.append(esito)
    print(('OK   ' if esito else 'NO   ') + cosa, flush=True)


srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5141', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_RULES=str(CART / 'r.json'), STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
API = "async ([n, a]) => { const r = await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json(); return r; }"
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5141/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate(API, [n, list(a)])  # noqa: E731
        for nome in ('Piastra A', 'Piastra B'):
            api('new_project', 'piastra', {'name': nome, 'larghezza': 200, 'altezza': 100, 'spessore': 10, 'foro': 20})
            api('save', str(CART / f'{nome}.steelcad'))
        api('new_assembly', 'Collegamento')
        api('asm_insert', str(CART / 'Piastra A.steelcad')); api('asm_insert', str(CART / 'Piastra B.steelcad'))
        api('save', str(CART / 'collegamento.steelcad-asm'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        # clic sulla faccia di sopra della prima piastra (la più alta con la normale in su)
        idx = pg.evaluate("""() => { const o = [...window.__steelcad.objs.values()][0]; const g = o.mesh.geometry, P = g.attributes.position;
            let best = null; for (const f of o.data.faces) { let z = -1e9; for (let k = f.start; k < f.start + f.count; k++) z = Math.max(z, P.getZ(g.index.getX(k)));
              const ok = [...Array(f.count).keys()].every(k => Math.abs(P.getZ(g.index.getX(f.start + k)) - z) < 1e-6);
              if (ok && (!best || z > best[0])) best = [z, f.index]; } return [o.data.id, best[1]]; }""")
        pg.evaluate("([id, f]) => window.__steelcad.select(id, f)", idx)
        pg.wait_for_selector('#a-nuovo', timeout=10000)
        ok('clic su una faccia piana: c’è «Nuovo pezzo su questa faccia»', pg.is_visible('#a-nuovo'))
        pg.click('#a-nuovo'); pg.wait_for_selector('#np-nome')
        pg.fill('#np-nome', 'Lamiera di collegamento'); pg.click('#m-ok')
        pg.wait_for_function('window.__steelcad.sketch', timeout=20000); time.sleep(1.2)
        v = pg.evaluate('window.__steelcad.sketch.v')
        refs = [l for l in v['lines'] if l.get('ref')]
        ok(f'sketch sul piano della faccia, con i bordi delle due piastre in arancio ({len(refs)} linee, '
           f'{sum(1 for c in v["circles"] if c.get("ref"))} fori)', len(refs) >= 8 and sum(1 for c in v['circles'] if c.get('ref')) == 2)
        ok('gli altri pezzi si vedono attorno (contesto)', pg.evaluate("window.__steelcad.state.mode") == 'part')
        pg.screenshot(path=str(SHOTS / '1_sketch_nel_contesto.png'))
        xs = [q['xy'][0] for q in v['points'] if q['id'] != 'O']; ys = [q['xy'][1] for q in v['points'] if q['id'] != 'O']
        sid = v['id']
        r = pg.evaluate("async ([sid, a, b]) => window.__steelcad.apply(await (await fetch('/api/sketch_add_rectangle', {method: 'POST', body: JSON.stringify([sid, a, b])})).json())",
                        [sid, [min(xs) + 100, min(ys) + 20], [max(xs) - 100, max(ys) - 20]])
        time.sleep(0.6)
        pg.click('#ribbon [data-make="sheet"]'); pg.wait_for_selector('#m-sp')
        pg.fill('#m-sp', '3'); pg.click('#m-ok')
        pg.wait_for_function('!window.__steelcad.sketch && window.__steelcad.state.sheet', timeout=30000); time.sleep(1)
        pg.screenshot(path=str(SHOTS / '2_lamiera_nel_contesto.png'))
        ok('«← Assieme» c’è', pg.is_visible('#b-back'))
        pg.click('#b-back'); pg.wait_for_function("window.__steelcad.state.mode === 'assembly'", timeout=20000); time.sleep(1.5)
        st = pg.evaluate('window.__steelcad.state')
        ok(f'tornati all’assieme: 3 pezzi ({len(st["tree"]["children"])} voci), senza avvisi', len([c for c in st['tree']['children'] if c['kind'] == 'instance']) == 3 and not st['warnings'])
        inter = api('asm_interferences').get('interferences', [])
        ok('nessuna interferenza (la lamiera appoggia sopra le piastre)', not inter)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
        pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '3_assieme.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
