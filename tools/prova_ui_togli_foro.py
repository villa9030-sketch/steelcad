"""Prova dell'interfaccia: un foro cliccato sul pezzo (vista 3D) si toglie da lì (28/10) — pulsante «Togli questo
foro» o Canc; gli altri fori dello stesso taglio restano; l'ultimo chiede di togliere il taglio intero. E i nomi
dei tagli nell'albero dicono cosa c'è.

    python tools/prova_ui_togli_foro.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5205', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5205/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
        sid = api('sketch_on_face', 'SM1/sopra')['sketch']
        for x in (50, 150, 250): api('sketch_add_circle', sid, [x, 100], 10)
        api('create_from_sketch', sid, 'cut', {})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.5)
        albero = pg.inner_text('#tree')
        chk('nell’albero il taglio si chiama «Fori 3 × Ø20»', 'Fori 3 × Ø20' in albero)

        def pareti():
            return pg.evaluate("(() => { const o = window.__steelcad.objs.get('body'); return o.data.faces.filter(f => (f.name || '').startsWith('TG1/parete')).map(f => f.index); })()")
        idx = pareti()
        chk(f'pareti dei fori nel 3D: {len(idx)}', len(idx) >= 3)
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        chk('pannello del foro con «Togli questo foro»', pg.is_visible('#h-togli'))
        pg.screenshot(path=str(OUT / '1_pannello.png'))
        pg.click('#h-togli'); time.sleep(2.5)
        st = api('state')
        chk('tolto un foro: «Fori 2 × Ø20»', 'Fori 2 × Ø20' in str(st['tree']))
        # Canc su un altro
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        idx = pareti()
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        pg.mouse.move(800, 450); pg.keyboard.press('Delete'); time.sleep(2.5)
        st = api('state')
        chk('Canc: ne resta uno, «Foro Ø20»', 'Foro Ø20' in str(st['tree']) and '2 ×' not in str(st['tree']))
        # l'ultimo: chiede di togliere il taglio
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        idx = pareti()
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        pg.click('#h-togli'); time.sleep(1)
        chk('l’ultimo: chiede di togliere il taglio intero', pg.is_visible('#modal-box') and 'unico' in pg.inner_text('#modal-box'))
        pg.screenshot(path=str(OUT / '2_ultimo.png'))
        pg.click('#m-ok'); time.sleep(2.5)
        chk('taglio tolto', "'sheet_cut'" not in str(api('state')['tree']))
        api('undo'); api('undo'); api('undo')
        chk('Annulla rimette i tre fori', 'Fori 3 × Ø20' in str(api('state')['tree']))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
