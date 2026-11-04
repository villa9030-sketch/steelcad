"""Prova dell'interfaccia di «Metti nel vano» (04/11) nel browser senza finestra: l'anta dell'ufficio (tubi 40×40,
traverso a 1100) e la pannellatura 1058 × 918 disegnata sdraiata (tests/data/vano). «Metti nel vano», clic sul
pannello, clic sul telaio vicino al vano sotto → pannello in piedi nel vano sotto, 1 mm per lato, a filo davanti;
il vano sopra (dove non ci sta) spento; In mezzo, Capovolgi; Fatto → tre accoppiamenti. Screenshot nella cartella.

    python tools/prova_ui_vano.py [cartella_screenshot] [porta]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_barra import comando  # noqa: F401  (comandi della barra, anche nei menu)

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5263
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'anta.steelcad', cart / 'ANTA UFFICIO.steelcad')
shutil.copy(ROOT / 'tests' / 'data' / 'vano' / 'pannello.steelcad', cart / 'PANNELLATURA INFERIORE.steelcad')
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
        r = pg.evaluate("async (a) => { const r = await (await fetch('/api/new_assembly_con_pezzi', {method: 'POST', body: JSON.stringify(a)})).json();"
                        " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }",
                        ['Ufficio', [{'path': str(cart / 'ANTA UFFICIO.steelcad')}, {'path': str(cart / 'PANNELLATURA INFERIORE.steelcad')}]])
        pg.wait_for_function("window.__steelcad.objs.size === 2", timeout=20000)
        time.sleep(0.8)
        pg.screenshot(path=str(out / 'vn1_assieme.png'))
        pg.evaluate("document.querySelectorAll('.toast').forEach(t => t.remove())")

        def schermo(iid, k):
            return pg.evaluate("""([iid, k]) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const f = o.data.faces.find(f => f.index === k); const pos = o.data.positions, idx = o.data.indices;
                const c = new T.Vector3(); let n = 0;
                for (let j = f.start; j < f.start + f.count; j++) { c.add(new T.Vector3(pos[idx[j]*3], pos[idx[j]*3+1], pos[idx[j]*3+2])); n++; }
                c.multiplyScalar(1 / n); c.applyMatrix4(o.mesh.matrixWorld);
                const q = c.clone().project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", [iid, k])

        def centro(iid):
            """Il centro del pezzo sullo schermo (il pannello sdraiato: il fondo che si vede)."""
            return pg.evaluate("""(iid) => { const S = window.__steelcad, T = S.THREE, o = S.objs.get(iid);
                const b = new T.Box3().setFromObject(o.mesh), c = b.getCenter(new T.Vector3());
                const q = c.project(S.camera); const r = document.querySelector('#c3d').getBoundingClientRect();
                return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; }""", iid)

        ok('pulsante «Metti nel vano» nella barra dell’assieme', pg.is_visible('[data-asm-tool="vano"]:has-text("Metti nel vano")'))
        ok('anche nella riga «Metti i pezzi al loro posto»', pg.is_visible('#asm-passo-vano'))
        comando(pg, '[data-asm-tool="vano"]')
        ok('suggerimento: il pannello da mettere', 'pannello da mettere' in pg.inner_text('#sk-help'))
        x, y = centro('I2')
        pg.mouse.move(x, y); time.sleep(0.2); pg.mouse.click(x, y); time.sleep(0.4)
        ok('poi chiede il telaio', 'telaio' in pg.inner_text('#sk-help'))
        # il traverso (in mezzo ai due vani): la sua faccia davanti
        traverso = pg.evaluate("""() => { const o = window.__steelcad.objs.get('I1'), P = o.data.positions, I = o.data.indices;
            let best = null;
            for (const f of o.data.faces) { let zs = 0, ys = 0, n = 0, z0 = 1e9, z1 = -1e9;
              for (let j = f.start; j < f.start + f.count; j++) { const z = P[I[j]*3+2]; zs += z; ys += P[I[j]*3+1]; n++; z0 = Math.min(z0, z); z1 = Math.max(z1, z); }
              if (ys / n < -19.9 && z1 - z0 < 41 && Math.abs(zs / n - 1120) < 5) best = f.index; }
            return best; }""")
        x, y = schermo('I1', traverso)
        y += 25                                                  # appena sotto il traverso: sul bordo del vano sotto
        pg.mouse.move(x, y); time.sleep(0.2)
        x2, y2 = schermo('I1', traverso)
        pg.mouse.click(x2, y2)
        pg.wait_for_selector('#vano [data-prof]', timeout=15000)
        time.sleep(0.6)
        pg.screenshot(path=str(out / 'vn2_anteprima.png'))
        t = pg.inner_text('#vano')
        ok('titolo con i due pezzi', 'PANNELLATURA INFERIORE' in t and 'ANTA UFFICIO' in t)
        ok('vano sotto scelto (920 × 1060)', pg.is_visible('#vano [data-vano="0"].on') and '920 × 1060' in t)
        ok('vano sopra spento: lì non ci sta', pg.is_disabled('#vano [data-vano="1"]'))
        ok('gioco 1 mm ai quattro lati', all(f'{lato} 1' in t for lato in ('sinistra', 'destra', 'sotto', 'sopra')))
        m = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('in anteprima il pannello è in piedi (spessore verso dietro)', abs(m[6] - 1) < 1e-6 and abs(m[3] - 41) < 1e-3 and abs(m[11] - 41) < 1e-3)
        ok('il vano in azzurro nel 3D', pg.evaluate("window.__vano.stato().ghost.children.length") == 3)
        pg.click('#vano [data-prof="mezzo"]'); time.sleep(0.8)
        ok('«In mezzo» acceso', pg.is_visible('#vano [data-prof="mezzo"].on'))
        pg.click('#vn-capo'); time.sleep(0.8)
        m2 = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('«Capovolgi»: le pieghe verso davanti', abs(m2[6] + 1) < 1e-6 or abs(m2[6] - m[6]) > 1)
        pg.screenshot(path=str(out / 'vn3_capovolto.png'))
        pg.click('#vn-capo'); time.sleep(0.8)
        pg.click('#vano [data-prof="davanti"]'); time.sleep(0.8)
        pg.click('#vn-ok')
        pg.wait_for_function("!window.__vano.stato().el", timeout=10000)
        time.sleep(1.5)
        pg.screenshot(path=str(out / 'vn4_fatto.png'))
        stato = pg.evaluate("JSON.stringify(window.__steelcad.state.tree)")
        ok('tre accoppiamenti nell’albero', stato.count('"kind":"mate"') == 3)
        ok('messaggio con il gioco', '1 mm per lato' in pg.inner_text('body'))
        m3 = pg.evaluate("window.__steelcad.objs.get('I2').data.matrix")
        ok('il pannello resta dove l’anteprima l’aveva messo', all(abs(a - b) < 1e-3 for a, b in zip(m3, m)))
        # Esc annulla senza muovere niente
        comando(pg, '[data-asm-tool="vano"]')
        x, y = centro('I2'); pg.mouse.click(x, y); time.sleep(0.3)
        x, y = schermo('I1', traverso); pg.mouse.click(x, y)
        pg.wait_for_selector('#vano [data-prof]', timeout=15000); time.sleep(0.4)
        pg.keyboard.press('Escape'); time.sleep(0.5)
        ok('Esc chiude e il pannello resta al suo posto', not pg.is_visible('#vano')
           and all(abs(a - b) < 1e-3 for a, b in zip(pg.evaluate("window.__steelcad.objs.get('I2').data.matrix"), m)))
        ok('nessun errore nella pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
sys.exit(0 if all(esiti) else 1)
