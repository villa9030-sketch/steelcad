"""Prova dell'interfaccia: gli accoppiamenti nuovi dalla barra in alto, cliccando le facce col mouse come l'utente.

    python tools/prova_ui_accoppiamenti.py [cartella]        (Python con Playwright; Chromium senza finestra)

Due piastre nell'assieme. Distanza (parte da quella che c'è, poi la scrivi), Angolo, Blocca; il pannello a
destra col campo giusto per ognuno.
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


# il punto sullo schermo del centro della faccia di iid con quella normale nel mondo (la più avanti lungo n)
SCHERMO = """([iid, n]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid), M = o.mesh.matrixWorld;
  const pos = o.data.positions, idx = o.data.indices; let best = null;
  const N = n ? new T.Vector3(...n) : S.camera.getWorldDirection(new T.Vector3()).negate();   // senza n: la più rivolta a me
  const P = k => new T.Vector3(pos[idx[k] * 3], pos[idx[k] * 3 + 1], pos[idx[k] * 3 + 2]).applyMatrix4(M);
  for (const f of o.data.faces) {
    let c = null, area = 0, big = 0, nn = new T.Vector3();      // il centro del triangolo più grande: sul pieno
    for (let k = f.start; k < f.start + f.count; k += 3) {
      const a = P(k), b = P(k + 1), d = P(k + 2), x = new T.Vector3().subVectors(b, a).cross(new T.Vector3().subVectors(d, a));
      const ar = x.length() / 2; if (!ar) continue;
      nn.add(x); area += ar; if (ar > big) { big = ar; c = a.add(b).add(d).multiplyScalar(1 / 3); } }
    if (!area || nn.normalize().dot(N) < (n ? 0.999 : 0.3)) continue;
    if (!n) { if (!best || nn.dot(N) > best.d) best = { c, i: f.index, d: nn.dot(N) }; continue; }
    if (!best || c.dot(N) > best.c.dot(N)) best = { c, i: f.index };
  }
  const q = best.c.clone().project(S.camera), r = document.querySelector('#c3d').getBoundingClientRect();
  return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height, best.i]; }"""

srv = subprocess.Popen([str(QUI / '.venv/Scripts/python.exe'), str(QUI / 'app/dev_server.py'), '--porta', '5143', '--cartella', str(CART)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_RULES=str(CART / 'r.json'), STEELCAD_HOME=str(CART)))
while not srv.stdout.readline().startswith(b'http'):
    pass
API = "async ([n, a]) => (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json()"
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        errori = []
        pg.on('pageerror', lambda e: errori.append(str(e)))
        pg.goto('http://127.0.0.1:5143/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate(API, [n, list(a)])  # noqa: E731
        for nome, L, H, sp in (('Base', 300, 200, 10), ('Piatto', 100, 100, 5)):
            api('new_project', 'piastra', {'name': nome, 'larghezza': L, 'altezza': H, 'spessore': sp, 'foro': 5})
            api('save', str(CART / f'{nome}.steelcad'))
        api('new_assembly', 'Accoppiamenti')
        api('asm_insert', str(CART / 'Base.steelcad')); api('asm_insert', str(CART / 'Piatto.steelcad'))
        api('asm_move', 'I2', 400, 0, 60)
        api('save', str(CART / 'accoppiamenti.steelcad-asm'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
        tutti = ['faccia', 'asse', 'distanza', 'angolo', 'tangente', 'parallelo', 'perpendicolare', 'centra', 'blocca']
        ok('nella barra in alto ci sono tutti e 9 gli accoppiamenti',
           all(pg.is_visible(f'#ribbon [data-asm-tool="{t}"]') for t in tutti))
        pg.screenshot(path=str(SHOTS / '1_barra.png'))

        def clic(iid, n):
            x, y, _ = pg.evaluate(SCHERMO, [iid, n])
            pg.mouse.move(x, y); time.sleep(0.15); pg.mouse.click(x, y); time.sleep(0.4)

        # Distanza: sopra della base, sopra del piatto (allineate), poi scrivo 40
        pg.click('#ribbon [data-asm-tool="distanza"]')
        ok('Distanza: chiede la faccia del pezzo fermo', 'pezzo che sta fermo' in pg.inner_text('#sk-help'))
        clic('I1', [0, 0, 1])
        ok('… poi quella dell’altro pezzo', 'altro pezzo' in pg.inner_text('#sk-help'))
        clic('I2', [0, 0, 1])
        pg.wait_for_selector('#m-off', timeout=15000)
        ok('il pannello si apre con la distanza che c’è (55) già selezionata',
           pg.input_value('#m-off').startswith('55') and pg.evaluate("document.activeElement.id") == 'm-off')
        pg.keyboard.type('40'); pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.tree.children.find(c => c.label === 'Accoppiamenti').children[0].label.includes('distanza 40')", timeout=15000)
        pg.keyboard.press('Escape'); time.sleep(0.6)
        m = [x for x in pg.evaluate("window.__steelcad.state.tree.children") if x['label'] == 'Accoppiamenti'][0]['children']
        ok(f'distanza 40 scritta: {m[0]["label"]}', 'distanza 40' in m[0]['label'])
        pg.screenshot(path=str(SHOTS / '2_distanza.png'))
        pg.click('#tree .node:has-text("M1")'); pg.wait_for_selector('#m-del'); pg.click('#m-del'); time.sleep(0.8)

        # Angolo: sopra della base, fianco del piatto (+X): 90° adesso, poi 30
        pg.click('#ribbon [data-asm-tool="angolo"]')
        clic('I1', [0, 0, 1]); clic('I2', [1, 0, 0])
        pg.wait_for_selector('#m-ang', timeout=15000)
        ok(f'Angolo: parte da quello che c’è ({pg.input_value("#m-ang")}°)', pg.input_value('#m-ang').startswith('90'))
        pg.keyboard.type('30'); pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.tree.children.find(c => c.label === 'Accoppiamenti').children.some(c => c.label.includes(', 30°'))", timeout=15000)
        pg.keyboard.press('Escape'); time.sleep(0.6)
        st = pg.evaluate('window.__steelcad.state')
        ok('angolo 30° rispettato, senza avvisi', not st['warnings'])
        pg.screenshot(path=str(SHOTS / '3_angolo.png'))

        # Blocca: due clic, il piatto resta dov'è
        prima = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix.map(x => x.toFixed(3)).join()")
        pg.click('#ribbon [data-asm-tool="blocca"]')
        ok('Blocca: chiede il pezzo che sta fermo', 'pezzo che sta fermo' in pg.inner_text('#sk-help'))
        clic('I1', [0, 0, 1]); clic('I2', None)
        pg.wait_for_function("window.__steelcad.state.tree.children.find(c => c.label === 'Accoppiamenti').children.length === 2", timeout=15000)
        pg.keyboard.press('Escape'); time.sleep(0.6)
        dopo = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix.map(x => x.toFixed(3)).join()")
        ok('Blocca: il piatto non si è mosso', prima == dopo)
        pg.click('#tree .node:has-text("M2")'); pg.wait_for_selector('#m-del')
        ok('pannello di Blocca: niente campo e niente «gira»', not pg.is_visible('#m-off') and not pg.is_visible('#m-flip'))
        pg.mouse.move(5, 895)
        pg.screenshot(path=str(SHOTS / '4_blocca.png'))
        ok('nessun errore in pagina', not errori)
        if errori:
            print(errori)
        b.close()
finally:
    srv.kill()
print(f'{sum(risultati)}/{len(risultati)} ok   foto in {SHOTS}')
