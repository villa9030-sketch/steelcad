"""Prova (03/11): «la distinta di taglio non posso ingrandirla o rimpicciolirla, come le viste». Nell'editor delle
tavole del telaio: clic sulla distinta di taglio, «+» due volte (120%), trascinata più in basso, poi la tavola
salvata ha la tabella grande e spostata.

    python tools/prova_ui_tabella_grandezza.py CARTELLA_FOTO [porta]
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
        k = pg.evaluate("window.__tavole.ED.fogli.findIndex(f => f.oggetti.some(o => o.id === 'tabella:taglio'))")
        chk('c’è un foglio con la distinta di taglio', k >= 0)
        pg.click(f'#te-tabs button[data-i="{k}"]'); time.sleep(1)
        bb0 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'tabella:taglio').bbox")
        pg.locator('#te-foglio [data-el="tabella:taglio"]').first.click(force=True); time.sleep(0.5)
        chk('pannello «Grandezza» della distinta di taglio', pg.is_visible('#ts-tpiu'))
        pg.screenshot(path=str(OUT / '1_selezionata.png'))
        pg.click('#ts-tpiu'); time.sleep(1.5)
        pg.locator('#te-foglio [data-el="tabella:taglio"]').first.click(force=True); time.sleep(0.4)
        pg.click('#ts-tpiu'); time.sleep(1.5)
        t = pg.evaluate("(window.__tavole.foglio().ritocchi.tabelle || {})['tabella:taglio']")
        chk(f'grandezza 120%: {t}', t and abs(t['k'] - 1.2) < 1e-6)
        bb1 = pg.evaluate("window.__tavole.foglio().oggetti.find(o => o.id === 'tabella:taglio').bbox")
        chk(f'più larga di 1,2 volte ({bb0[2]-bb0[0]:.1f} -> {bb1[2]-bb1[0]:.1f})', abs((bb1[2] - bb1[0]) - 1.2 * (bb0[2] - bb0[0])) < 1)
        # trascinata di 30 mm in giù sul foglio
        box = pg.locator('#te-foglio [data-el="tabella:taglio"]').first.bounding_box()
        x, y = box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.3
        mmpx = pg.evaluate("""() => { const svg = document.querySelector('#te-foglio svg'); return svg.getBoundingClientRect().width / window.__tavole.foglio().size[0]; }""")
        pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x, y + 15 * mmpx, steps=6); pg.mouse.move(x, y + 30 * mmpx, steps=6); pg.mouse.up(); time.sleep(1.8)
        t = pg.evaluate("(window.__tavole.foglio().ritocchi.tabelle || {})['tabella:taglio']")
        chk(f'spostata in giù di circa 30 mm: {t}', t and t.get('d') and abs(t['d'][1] + 30) < 3 and abs(t['d'][0]) < 3)
        chk('nell’elenco dei ritocchi', 'Distinta di taglio al 120%, spostata' in pg.inner_text('#te-rit'))
        pg.screenshot(path=str(OUT / '2_grande_spostata.png'))
        svg = pg.evaluate("window.__tavole.foglio().svg")
        pg2 = b.new_page(viewport={'width': 1800, 'height': 1273})
        pg2.set_content('<html><body style="margin:0;background:#fff">' + svg.replace('<svg', '<svg style="width:1800px;height:auto"', 1) + '</body></html>')
        pg2.screenshot(path=str(OUT / '3_tavola.png'), full_page=True); pg2.close()
        chk('nessun errore nella pagina ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok_tutti)}/{len(ok_tutti)}')
