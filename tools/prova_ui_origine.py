"""Prova dell'interfaccia: i bordi arancio che vengono da un taglio (24/10) — Canc non dà più «non si cancellano»:
dice da quale taglio vengono e li toglie da lì, apre quel disegno, o toglie tutto il taglio.

    python tools/prova_ui_origine.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5202', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5202/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
        sid = api('sketch_on_face', 'SM1/sopra')['sketch']
        for x in (50, 150, 250): api('sketch_add_circle', sid, [x, 100], 10)
        api('create_from_sketch', sid, 'cut', {})
        nuovo = api('sketch_on_face', 'SM1/sopra')['sketch']
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1)
        pg.evaluate("window.__steelcad.hideHome()")
        pg.evaluate("sid => window.__steelcad.enterSketch(sid)", nuovo); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
        cerchi = pg.evaluate("window.__steelcad.sketch.v.circles.filter(c => c.ref).map(c => c.id)")
        chk(f'cerchi arancio nello sketch nuovo: {len(cerchi)}', len(cerchi) == 3)
        def scegli(ids):
            pg.evaluate("ids => { const S = window.__steelcad.sketch; S.sel.clear(); ids.forEach(i => S.sel.add(i)); }", ids)
            pg.mouse.move(700, 450); pg.keyboard.press('Delete'); time.sleep(1.2)
        scegli(cerchi[:2])
        chk('barra: da quale taglio vengono', pg.is_visible('#sk-origine') and 'TG' in pg.inner_text('#sk-origine'))
        chk('niente più «non si cancellano»', 'non si cancellano' not in pg.inner_text('#toasts'))
        pg.screenshot(path=str(OUT / '1_barra.png'))
        pg.click('#or-togli'); time.sleep(3)
        st = api('state')
        rimasti = pg.evaluate("window.__steelcad.sketch.v.circles.filter(c => c.ref).length")
        chk(f'due fori tolti dal taglio, bordi rifatti: {rimasti} cerchi arancio', rimasti == 1)
        pg.screenshot(path=str(OUT / '2_tolti.png'))
        api('undo'); pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1)
        pg.evaluate("window.__steelcad.hideHome()")
        pg.evaluate("sid => window.__steelcad.enterSketch(sid)", nuovo); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
        chk('Annulla li rimette', pg.evaluate("window.__steelcad.sketch.v.circles.filter(c => c.ref).length") == 3)
        # apri il disegno di quel taglio
        scegli(cerchi[:1]); pg.click('#or-apri'); time.sleep(1.5)
        chk(f'aperto il disegno del taglio ({sid})', pg.evaluate("window.__steelcad.sketch?.sid") == sid)
        # togli tutto il taglio
        pg.evaluate("window.__steelcad.exitSketch()"); time.sleep(0.8)
        chk('lo sketch vuoto lasciato si toglie da solo', not any(f == nuovo for f in str(api('state')['tree']).split("'")))
        nuovo = api('sketch_on_face', 'SM1/sopra')['sketch']
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1); pg.evaluate("window.__steelcad.hideHome()")
        pg.evaluate("sid => window.__steelcad.enterSketch(sid)", nuovo); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1)
        cerchi = pg.evaluate("window.__steelcad.sketch.v.circles.filter(c => c.ref).map(c => c.id)")
        scegli(cerchi); pg.click('#or-tutto'); time.sleep(0.8)
        chk('chiede conferma per tutto il taglio', pg.is_visible('#modal-box') and 'Elimina' in pg.inner_text('#modal-box'))
        pg.click('#m-ok'); time.sleep(2.5)
        st = api('state')
        chk('taglio tolto: niente più fori', 'Taglio attraverso' not in str(st['tree']))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
