r"""Prova dell'interfaccia (03/11, dal collaudo): clicchi un altro lato mentre la piega si sta costruendo. Il pezzo
rifatto numera le facce in un altro modo: il pannello deve restare sul lato cliccato (prima finiva sulla «Scatola»,
la faccia che nel pezzo nuovo aveva il numero del lato di prima). Vince l'ultimo clic.

    <python con playwright> tools\prova_ui_clic_svelto.py cartella_screenshot
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = 5216


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    cart = Path(tempfile.mkdtemp())
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, cwd=str(ROOT),
                           env=dict(os.environ, STEELCAD_RULES=str(cart / 'regole_lamiera.json')))
    while not srv.stdout.readline().startswith(b'http'):
        pass
    buono = False
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=__import__('os').environ.get('RADIUS_CHROME'), args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1500, 'height': 900})
            pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
            pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
            pg.evaluate("fetch('/api/new_project', {method: 'POST', body: JSON.stringify(['lamiera', "
                        "{name: 'Scatola', larghezza: 400, profondita: 300, spessore: 2, raggio: 2, k: 0.5}])})")
            time.sleep(0.5)
            pg.reload()
            pg.wait_for_function("window.__steelcad && window.__steelcad.ready && window.__steelcad.objs.has('body')")
            # clic sul lato destro (L2) col pezzo di prima
            pg.evaluate("""() => { const o = window.__steelcad.objs.get('body');
                const f = o.data.faces.find(x => x.name === 'SM1/lato/L2'); window.__steelcad.select('body', f.index); }""")
            pg.wait_for_selector('#f-add')
            print('   prima:', pg.inner_text('#f-add'), flush=True)
            # intanto la piega davanti finisce e arriva il pezzo nuovo: le facce cambiano numero (il lato destro
            # era la faccia 1, nel pezzo nuovo la 1 è il sotto della base)
            pg.evaluate("""async () => { const c = (n, ...a) => fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json());
                await c('add_flange', 'SM1', 'L1', {length: '60'}); const st = await c('state');
                await window.__steelcad.apply({ok: true, state: st.state || st}); }""")
            time.sleep(1.0)
            c = pg.locator('#f-add').count()
            t = pg.inner_text('#f-add') if c else '(niente: ' + pg.evaluate("(document.querySelector('#props h3') || {}).innerText || ''") + ')'
            buono = c == 1 and 'destro' in t
            print(('OK  ' if buono else 'NO  ') + f'clic su un altro lato mentre la piega si costruiva: il pannello resta lì ({t!r})', flush=True)
            pg.screenshot(path=str(SHOTS / 'clic_svelto.png'))
            b.close()
    finally:
        srv.kill()
    sys.exit(0 if buono else 1)


if __name__ == '__main__':
    main()
