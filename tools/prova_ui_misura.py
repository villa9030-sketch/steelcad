"""Prova dell'interfaccia: la Quota (misura) dappertutto — due vertici, il diametro di un foro, lo sviluppo, un assieme.

    python tools/prova_ui_misura.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5177', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
SCR = """(p) => { const r = document.querySelector('#c3d').getBoundingClientRect(), a = window.__steelcad.toScreen(p); return [r.left + a[0], r.top + a[1]]; }"""
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1400, 'height': 850}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.add_init_script("try { localStorage.setItem('steelcad.tema', 'scuro'); } catch {}")
        pg.goto('http://127.0.0.1:5177/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'L', 'larghezza': 300, 'profondita': 200, 'spessore': 2})
        api('add_flange', 'SM1', 'L1', {'length': '50'})
        sid = api('sketch_on_face', 'SM1/sopra')['sketch']; api('sketch_add_circle', sid, [150, 100], 10); api('create_from_sketch', sid, 'cut', {})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        chk('pulsante Quota nella barra', pg.is_visible('.rbody:not([hidden]) [data-cmd="misura"]'))
        pg.click('.rbody:not([hidden]) [data-cmd="misura"]'); time.sleep(0.3)
        def clic(p3):
            x, y = pg.evaluate(SCR, p3); pg.mouse.move(x, y, steps=3); time.sleep(0.3); pg.mouse.click(x, y); time.sleep(0.4)
        clic([0, 200, 2]); clic([300, 200, 2])
        et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
        chk(f'quota tra due vertici: {et}', et and et[0].replace('.', '').replace(',', '.').startswith('300'))
        x, y = pg.evaluate(SCR, [160, 100, 2]); pg.mouse.move(x, y, steps=3); time.sleep(0.3)
        clic([160, 100, 2])                         # il bordo del foro Ø20
        et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
        chk(f'diametro del foro: {et}', any(e.startswith('Ø20') for e in et))
        pg.screenshot(path=str(OUT / 'pezzo.png'))
        # nello sviluppo
        pg.keyboard.press('Escape'); pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(1.5)
        pg.keyboard.press('m'); time.sleep(0.3)
        chk('Quota accesa col tasto M', pg.evaluate("document.querySelector('#ribbon [data-cmd=\"misura\"]').classList.contains('on')"))
        pg.screenshot(path=str(OUT / 'sviluppo.png'))
        # in un assieme
        f = cart / 'L.steelcad'; api('save', str(f)); api('new_assembly', 'A'); api('asm_insert', str(f)); api('asm_insert', str(f))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        chk('pulsante Quota nell’assieme', pg.is_visible('.rbody:not([hidden]) [data-cmd="misura"]'))
        pg.click('.rbody:not([hidden]) [data-cmd="misura"]'); time.sleep(0.3)
        T2 = pg.evaluate("[...window.__steelcad.objs.values()].filter(o => o.data.kind === 'instance').map(o => o.data.matrix)")
        dx = T2[1][3] - T2[0][3]
        clic([0, 200, 2]); clic([dx, 200, 2])
        et = pg.evaluate("[...document.querySelectorAll('#mis-box .dim')].map(e => e.textContent)")
        chk(f'quota tra due pezzi dell’assieme (atteso {dx:.2f}): {et}', len(et) == 1)
        pg.screenshot(path=str(OUT / 'assieme.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
