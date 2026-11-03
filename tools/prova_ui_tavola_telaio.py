"""Prova (03/11): il telaio 807 × 725 × 795 in 30×30×2 con la croce sopra e i fianchi divisi (incroci): la distinta
di taglio e le tavole della struttura, rese come immagini.

    python tools/prova_ui_tavola_telaio.py CARTELLA_FOTO [porta]
"""
import os, subprocess, tempfile, time, sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright
W = Path(__file__).resolve().parents[1]; PY = sys.executable
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
PORTA = sys.argv[2] if len(sys.argv) > 2 else '5266'
tmp = Path(tempfile.mkdtemp())
srv = subprocess.Popen([PY, str(W / 'app/dev_server.py'), '--porta', PORTA, '--cartella', str(tmp)], cwd=str(W),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(tmp / '.sc'), USERPROFILE=str(tmp)))
while not srv.stdout.readline().startswith(b'http'): pass
def log(*a): print(*a, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        r = api('new_project', 'telaio', {'name': 'Telaio 807', 'L': 807, 'P': 725, 'H': 795, 'ripiano': 0, 'profilo': '30x30x2', 'gambe': '30x30x2'})
        log('telaio', r.get('ok'), r.get('message'))
        objs = [o for o in api('scene')['objects'] if o['kind'] == 'member']
        nome = lambda pre: next(o['id'].split('/')[1] for o in objs if o['name'].startswith(pre))
        api('add_traverso', 'ST1', nome('Traverso davanti'), nome('Traverso dietro'), 388.5, 'sotto', '30x30x2', False, '')
        api('add_traverso', 'ST1', nome('Fianco a sinistra'), nome('Fianco a destra'), 347.5, 'sotto', '30x30x2', False, '')
        for lato in ('Fianco a sinistra', 'Fianco a destra'):
            r = api('punto_su_tubo', 'ST1', nome(lato), 347.5)
            r = api('tubo_da_angolo', 'ST1', r['node'].split(':')[1], 'giu', 795, '30x30x2', ''); log('montante', r.get('ok'))
        objs = [o for o in api('scene')['objects'] if o['kind'] == 'member']
        for g in ('Gamba davanti a sinistra', 'Gamba davanti a destra'):
            r = api('punto_su_tubo', 'ST1', nome(g), 383)
            r = api('tubo_da_angolo', 'ST1', r['node'].split(':')[1], 'dietro', 725, '30x30x2', ''); log('traverso fianco', r.get('ok'))
        api('save', str(tmp / 'Telaio banco 807.steelcad'))
        cl = api('state').get('cutlist') or {}
        for r_ in cl.get('rows', []):
            log('riga', r_.get('length_mm'), r_.get('qty'), r_.get('cuts'), r_.get('groups'), r_.get('nomi'), r_.get('members'))
        prev = api('drawing_preview', None, True)
        log('tavole', prev.get('ok'), prev.get('message'), len(prev.get('sheets') or []))
        for i, s in enumerate(prev.get('sheets') or [], 1):
            (OUT / f'tav{i}.svg').write_text(s['svg'], encoding='utf-8')
            pg2 = b.new_page(viewport={'width': 1800, 'height': 1273})
            pg2.set_content('<html><body style="margin:0;background:#fff">' + s['svg'].replace('<svg', '<svg style="width:1800px;height:auto"', 1) + '</body></html>')
            pg2.screenshot(path=str(OUT / f'tav{i}.png'), full_page=True); pg2.close()
        # nell'app: la distinta di taglio in basso e il «Prepara per l'officina»
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(2)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        pg.evaluate("document.querySelector('.tabs button[data-tab=cut]').click()"); time.sleep(0.3)
        if pg.is_visible('#bottom-toggle') and 'bottom-closed' in (pg.get_attribute('body', 'class') or ''): pg.click('#bottom-toggle'); time.sleep(0.5)
        pg.screenshot(path=str(OUT / 'app_distinta_taglio.png'))
        pg.click('#b-prepara'); time.sleep(2.5)
        pg.screenshot(path=str(OUT / 'app_prepara.png'))
        pg.click('#m-ok'); time.sleep(5)
        pg.screenshot(path=str(OUT / 'app_prepara_fatto.png'))
        info = api('prepara_info'); log('prepara', [(v['id'], v['si'], v['file']) for v in info['voci']])
        r = api('prepara', str(tmp / 'uscita'), ['officina', 'taglio'], None); log('prepara fatto', r)
        log('file', sorted(x.name for x in (tmp / 'uscita').iterdir()) if (tmp / 'uscita').exists() else None)
        import shutil                                   # il file Excel per la troncatrice, da aprire e guardare
        for x in (tmp / 'uscita').glob('*_taglio.xlsx'):
            shutil.copy(x, OUT / x.name); log('excel', OUT / x.name)
        log('errori pagina', err)
        b.close()
finally:
    srv.kill()
