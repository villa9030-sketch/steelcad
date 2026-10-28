"""Prova dell'interfaccia: la tramoggia fatta è un pezzo come gli altri (28/10) — i comandi della lamiera si vedono,
si disegna su una parete cliccata, sullo sviluppo, e i bordi liberi si accendono per piegarli.

    python tools/prova_ui_tramoggia.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5203', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5203/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'tramoggia_cassone', {'raggio': 3, 'k': 0.4})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.5)
        pg.click('[data-rtab="lamiera"]')
        time.sleep(0.4)
        vis = lambda sel: pg.evaluate("s => { const b = document.querySelector(s); return !!b && !b.hidden && !b.disabled; }", sel)
        chk('«Su una faccia» si vede', vis('#ribbon [data-cmd="face_help"]'))
        chk('«Sullo sviluppo» si vede', vis('#ribbon [data-cmd="flat_sketch"]'))
        chk('«Taglio» si vede', vis('#ribbon [data-azione="taglia"]'))
        chk('«Linguetta» si vede', vis('#ribbon [data-azione="linguetta"]'))
        chk('«Piega» (bordo libero) si vede', vis('#ribbon [data-cmd="flange_help"]'))
        chk('«Orlo» resta nascosto (le pieghe della forma sono i suoi spigoli)', not vis('#ribbon [data-azione="orlo"]'))
        pg.screenshot(path=str(OUT / '1_comandi.png'))
        sc = api('scene')
        bordi = [e for e in sc['bend_edges']]
        chk(f'bordi liberi da piegare: {len(bordi)}', len(bordi) >= 4)
        # una parete cliccata → Taglio disegna lì
        idx = pg.evaluate("(() => { const o = window.__steelcad.objs.get('body'); return o ? (o.data.faces.find(f => f.name === 'FM1/cassone_destra/fuori') || {}).index : null; })()")
        if idx is not None:
            pg.evaluate("i => window.__steelcad.select('body', i)", idx); time.sleep(1)
            pg.click('#ribbon [data-azione="taglia"]'); pg.wait_for_function('window.__steelcad.sketch', timeout=10000); time.sleep(0.8)
            chk('Taglio: sketch sulla parete cliccata', 'cassone destra' in str(api('state')['tree']))
            pg.screenshot(path=str(OUT / '2_sketch_parete.png'))
            pg.evaluate("window.__steelcad.exitSketch()"); time.sleep(0.8)
        else:
            chk('indice della parete trovato', False)
        # sullo sviluppo: un foro nella falda davanti
        sid = api('sketch_on_flat', 'FM1')['sketch']
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        pg.evaluate("sid => window.__steelcad.enterSketch(sid)", sid); pg.wait_for_function('window.__steelcad.sketch'); time.sleep(1.2)
        n_ref = pg.evaluate("window.__steelcad.sketch.v.lines.filter(l => l.ref).length")
        chk(f'sullo sviluppo si vedono i pezzi della tramoggia ({n_ref} linee arancio)', n_ref > 20)
        pg.screenshot(path=str(OUT / '3_sviluppo.png'))
        # 29/10: il bordo in alto con gli angoli a 45° (un anello solo nel 3D): ci si disegna e si fora
        api('new_project', 'tramoggia_cassone', dict(A=600, B=600, Hc=600, a=250, b=250, Ht=400, bordo=20, verso_bordo='dentro',
                                                     flangia=50, verso_flangia='fuori', angoli_bordo='45', spessore=2, raggio=2,
                                                     k=0.4, divisione='lati'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        idx = pg.evaluate("(() => { const o = window.__steelcad.objs.get('body'); const f = o.data.faces.find(f => /^FM1\/bordo_[a-z]+\/fuori$/.test(f.name || '')); window.__nomeBordo = f && f.name; return f ? f.index : null; })()")
        chk('l’anello del bordo ha un nome nel 3D', idx is not None)
        pg.evaluate("i => window.__steelcad.select('body', i)", idx); time.sleep(1.2)
        chk('cliccandolo: «Disegna su questa faccia»', pg.is_visible('[data-face-sketch]'))
        pg.screenshot(path=str(OUT / '4_bordo.png'))
        pg.click('[data-face-sketch]'); pg.wait_for_function('window.__steelcad.sketch', timeout=10000); time.sleep(0.8)
        sid = pg.evaluate("window.__steelcad.sketch.sid")
        bb = pg.evaluate("(() => { const v = window.__steelcad.sketch.v; const xs = v.points.map(p => p.xy[0]), ys = v.points.map(p => p.xy[1]); return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]; })()")
        print('  ingombro del disegno', bb)
        r = api('fori_guidati', pg.evaluate('window.__nomeBordo'), {'tipo': 'tondo', 'd': 8, 'x': 300, 'y': 10})
        chk('foro sul bordo: ' + str(r.get('message')), r.get('ok'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
