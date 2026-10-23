"""Prova dell'interfaccia: pezzi e lavori spostati (23/10) — la striscia «pezzi non trovati» con Cerca… nell'assieme,
il lavoro spostato in grigio nella pagina iniziale.

    python tools/prova_ui_spostati.py [cartella]
"""
import os, shutil, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5186', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1400, 'height': 850}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.add_init_script("try { localStorage.setItem('steelcad.tema', 'scuro'); } catch {}")
        pg.goto('http://127.0.0.1:5186/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        # nel server di prova «Salva» scrive nella sua cartella: poi i file si spostano a mano, come ha fatto Stefano
        for nome, w in (('Fondo', 400), ('Parete A', 300)):
            api('new_project', 'lamiera', {'name': nome, 'larghezza': w, 'profondita': 100, 'spessore': 2}); api('save', False)
        api('new_assembly_con_pezzi', 'Scatola', [{'path': str(cart / 'Fondo.steelcad'), 'n': 1}, {'path': str(cart / 'Parete A.steelcad'), 'n': 2}])
        api('save', False)
        (cart / 'archivio' / 'pezzi').mkdir(parents=True); (cart / 'lavori').mkdir()
        for nome in ('Fondo', 'Parete A'):
            shutil.move(str(cart / f'{nome}.steelcad'), str(cart / 'archivio' / 'pezzi' / f'{nome}.steelcad'))
        shutil.move(str(cart / 'Scatola.steelcad-asm'), str(cart / 'lavori' / 'Scatola.steelcad-asm'))
        pezzi_ora = cart / 'archivio' / 'pezzi'
        print('apri', api('open_path', str(cart / 'lavori' / 'Scatola.steelcad-asm'), False).get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        chk('striscia dei pezzi non trovati', pg.is_visible('#mancanti') and pg.locator('[data-cerca-pezzo]').count() == 2)
        pg.screenshot(path=str(OUT / '1_mancanti.png'))
        vecchio = pg.get_attribute('[data-cerca-pezzo] >> nth=0', 'data-cerca-pezzo')
        r = api('asm_ritrova_in', vecchio, str(pezzi_ora / Path(vecchio).name))
        chk('Cerca: ' + r.get('message', ''), r.get('ok'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        chk('striscia sparita, 3 pezzi a video', not pg.is_visible('#mancanti') and len(api('state')['instances']) == 3)
        pg.screenshot(path=str(OUT / '2_ritrovati.png'))
        # pagina iniziale: l'assieme spostato resta in grigio
        shutil.move(str(cart / 'lavori' / 'Scatola.steelcad-asm'), str(cart / 'archivio' / 'Scatola.steelcad-asm'))
        pg.evaluate("window.__steelcad.runCmd('home')"); time.sleep(1.2)
        chk('recente spostato in grigio', pg.locator('.home-rec.manca').count() >= 1 and pg.locator('[data-ritrova]').count() >= 1)
        pg.screenshot(path=str(OUT / '3_home.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
