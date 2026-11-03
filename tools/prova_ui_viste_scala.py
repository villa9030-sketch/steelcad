"""Prova (03/11): «e le viste?». Nell'editor delle tavole del telaio: clic sulla vista di fronte, Scala 1:20 (tutte
le viste, il cartiglio la scrive); clic sull'isometrica, «+» due volte (120%).

    python tools/prova_ui_viste_scala.py CARTELLA_FOTO [porta]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[2] if len(sys.argv) > 2 else '5267'
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
        api('new_project', 'telaio', {'name': 'Telaio 807', 'L': 807, 'P': 725, 'H': 795, 'ripiano': 0, 'profilo': '30x30x2', 'gambe': '30x30x2'})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.4)
        pg.evaluate("window.__steelcad.runCmd('drawings')")
        pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(0.8)
        pg.locator('#te-foglio [data-el="vista:fronte"]').first.click(force=True); time.sleep(0.5)
        chk('«Scala» nel pannello della vista', pg.is_visible('#ts-scala'))
        chk('dice la scala di adesso: ' + pg.inner_text('#ts-scala option[value=""]'), '1:15' in pg.inner_text('#ts-scala option[value=""]'))
        T0 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'vista:fronte').T[0]")
        iso0 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'vista:iso').bbox")
        pg.select_option('#ts-scala', '1:20'); time.sleep(4)
        T1 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'vista:fronte').T[0]")
        chk(f'viste in 1:20 ({T0:.4f} -> {T1:.4f})', abs(T1 - T0 * 15 / 20) < 1e-3)
        chk('il cartiglio dice 1:20', '>1:20<' in pg.inner_html('#te-foglio'))
        pg.screenshot(path=str(OUT / '1_viste_1_20.png'))
        pg.locator('#te-foglio [data-el="vista:iso"]').first.click(force=True); time.sleep(0.5)
        chk('«Grandezza» nel pannello dell’isometrica', pg.is_visible('#ts-ipiu'))
        pg.click('#ts-ipiu'); time.sleep(4)
        pg.locator('#te-foglio [data-el="vista:iso"]').first.click(force=True); time.sleep(0.4)
        pg.click('#ts-ipiu'); time.sleep(4)
        R = pg.evaluate("window.__tavole.foglio().ritocchi")
        iso1 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'vista:iso').bbox")
        chk(f'isometrica al 120%: {R}', R.get('iso') == 1.2 and R.get('scala') == '1:20')
        chk(f'isometrica più grande ({iso0[2]-iso0[0]:.0f} -> {iso1[2]-iso1[0]:.0f} mm)', (iso1[2] - iso1[0]) > 1.1 * (iso0[2] - iso0[0]))
        chk('nell’elenco dei ritocchi', 'Viste in scala 1:20' in pg.inner_text('#te-rit') and 'Isometrica al 120%' in pg.inner_text('#te-rit'))
        pg.screenshot(path=str(OUT / '2_iso_120.png'))
        svg = pg.evaluate("window.__tavole.foglio().svg")
        pg2 = b.new_page(viewport={'width': 1800, 'height': 1273})
        pg2.set_content('<html><body style="margin:0;background:#fff">' + svg.replace('<svg', '<svg style="width:1800px;height:auto"', 1) + '</body></html>')
        pg2.screenshot(path=str(OUT / '3_tavola.png'), full_page=True); pg2.close()
        chk('nessun errore nella pagina ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok_tutti)}/{len(ok_tutti)}')
