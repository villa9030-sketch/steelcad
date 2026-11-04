"""Prova (04/11, pannello parete): «perché da questi tagli non posso fare le pieghe?». In una lamiera con una finestra
tagliata, i lati della finestra si accendono col mouse e il clic apre la piega; i quattro risvolti si fanno e lo
sviluppo è giusto.

    python tools/prova_ui_risvolti_finestra.py CARTELLA_FOTO [porta]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[2] if len(sys.argv) > 2 else '5269'
tmp = Path(tempfile.mkdtemp())
srv = subprocess.Popen([PY, str(W / 'app/dev_server.py'), '--porta', PORTA, '--cartella', str(tmp)], cwd=str(W),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp)))
while not srv.stdout.readline().startswith(b'http'): pass
ok_tutti = []
def chk(t, v): ok_tutti.append(bool(v)); print(('OK  ' if v else 'NO  ') + t, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'Pannello', 'larghezza': 600, 'profondita': 400, 'spessore': 2, 'raggio': 1, 'k': 0.4})
        sk = api('sketch_on_face', 'SM1/sopra')['sketch']
        api('sketch_add_rectangle', sk, [100, 80], [500, 320])
        chk('finestra tagliata', api('create_from_sketch', sk, 'cut', {}).get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(1)
        liberi = pg.evaluate("window.__steelcad.bendEdges.filter(e => e.kind === 'libero').length")
        chk(f'i 4 lati della finestra sono bordi da piegare ({liberi})', liberi == 4)
        canvas = pg.locator('#c3d').bounding_box()
        x, y = pg.evaluate("""() => { const sc = window.__steelcad, e = sc.bendEdges.filter(x => x.kind === 'libero').sort((a, b) => b.length - a.length)[0];
            return sc.toScreen(e.a.map((v, i) => (v + e.b[i]) / 2)); }""")
        pg.mouse.move(canvas['x'] + x, canvas['y'] + y); time.sleep(0.4)
        pg.screenshot(path=str(OUT / '1_bordo_acceso.png'))
        pg.mouse.click(canvas['x'] + x, canvas['y'] + y); time.sleep(1.2)
        chk('clic sul lato: si apre «Piega su questo bordo» con l’anteprima', 'Piega su questo bordo' in pg.inner_text('#props'))
        pg.screenshot(path=str(OUT / '2_clic_lato.png'))
        # i quattro risvolti, come li fa il pannello della piega
        fatti = 0
        for lato in (400, 240, 400, 240):
            e = max((x for x in api('scene')['bend_edges'] if x['kind'] == 'libero' and x['face'] == 'SM1/sopra'
                     and abs(x['length'] - lato) < 25), key=lambda x: x['length'])
            fatti += bool(api('add_edge_flange', e['face'], e['ea'], e['eb'], {'length': '20', 'angle': '90', 'direction': 'down'}).get('ok'))
        chk(f'4 risvolti fatti ({fatti})', fatti == 4)
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(1.5)
        pg.screenshot(path=str(OUT / '3_risvolti.png'))
        pg.evaluate("window.__steelcad.runCmd('unfold')"); time.sleep(2.5)
        pg.screenshot(path=str(OUT / '4_sviluppo.png'))
        chk('nessun errore nella pagina ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok_tutti)}/{len(ok_tutti)}')
