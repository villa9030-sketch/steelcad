"""Prova (04/11, porta ugelli): «Togli materiale» sulla griglia di quadrati dava «Così non si può fare» per una tasca
passante fatta il 02/11 sulla piega. Ora: file vecchio aperto, Togli materiale va; con una tasca non passante il
messaggio dice quale lavorazione blocca e si legge tutto; i campi delle Misure mostrano 14,325 per intero.

    python tools/prova_ui_tasca_lamiera.py CARTELLA_FOTO [porta]
"""
import json, os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[2] if len(sys.argv) > 2 else '5268'
tmp = Path(tempfile.mkdtemp())
d = json.loads((W / 'tests/data/porta_ugelli_tasca.steelcad').read_text(encoding='utf-8'))
(tmp / 'porta.steelcad').write_text(json.dumps(d), encoding='utf-8')
for f in d['features']:
    if f['id'] == 'E1':
        f.pop('through_all'); f['distance'] = 1; f['name'] = 'Tasca'
(tmp / 'tasca.steelcad').write_text(json.dumps(d), encoding='utf-8')
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

        def apri(nome):
            r = api('open_path', str(tmp / nome)); assert r.get('ok'), r
            pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000); time.sleep(1.5)
            pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.4)
            pg.evaluate("window.__steelcad.enterSketch('S16')"); time.sleep(2.5)
            pg.screenshot(path=str(OUT / f'0_{nome}.png'))
            pg.click('#sk-face [data-make="cut"]')
            try:
                pg.wait_for_function("document.querySelector('#prova-barra.si, #prova-barra.no') || !window.__steelcad.sketch",
                                     timeout=180000)
            except Exception:
                pg.screenshot(path=str(OUT / f'0_{nome}_bloccata.png')); raise
            time.sleep(0.8)

        apri('porta.steelcad')
        if pg.is_visible('#prova-barra.si'):          # con l'anteprima: si conferma
            pg.click('#pr-ok'); pg.wait_for_function("!window.__steelcad.sketch", timeout=180000)
        time.sleep(1.5)
        chk('file del 02/11: la griglia si toglie (disegno chiuso)', not pg.evaluate('!!window.__steelcad.sketch'))
        ko = pg.evaluate("[...document.querySelectorAll('#tree .node.err')].map(n => n.innerText)")
        chk(f'nessuna lavorazione in errore {ko}', not ko)
        chk('la tasca è diventata un taglio della lamiera', 'tasca passante' not in pg.inner_text('#tree').lower())
        w = pg.evaluate("[...document.querySelectorAll('#params input.field')].map(i => i.scrollWidth <= i.clientWidth + 1)")
        chk(f'campi delle Misure leggibili per intero ({sum(w)}/{len(w)})', w and all(w))
        pg.screenshot(path=str(OUT / '2_tagliato.png'))

        apri('tasca.steelcad')
        chk('con la tasca non passante: rosso', pg.is_visible('#prova-barra.no'))
        t = pg.inner_text('#prova-barra .frase small')
        chk(f'il messaggio nomina la Tasca: {t!r}', '«Tasca»' in t)
        sm = pg.evaluate("(() => { const s = document.querySelector('#prova-barra .frase small'); return s.scrollWidth <= s.clientWidth + 1; })()")
        chk('il messaggio si legge tutto (niente «…»)', sm)
        pg.screenshot(path=str(OUT / '3_messaggio.png'))
        pg.set_viewport_size({'width': 1366, 'height': 768}); time.sleep(0.8)
        pg.screenshot(path=str(OUT / '4_messaggio_1366.png'))
        chk('nessun errore nella pagina ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok_tutti)}/{len(ok_tutti)}')
