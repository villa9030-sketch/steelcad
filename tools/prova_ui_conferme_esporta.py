"""Prova dell'interfaccia: dopo ogni esportazione (DXF, STEP, tavole PDF, Excel) la conferma col nome del file, la
cartella e «Apri la cartella» (03/11).

    python tools/prova_ui_conferme_esporta.py [cartella_screenshot] [porta]
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5272
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=env)
while not srv.stdout.readline().startswith(b'http'):
    pass
esiti = []


def ok(t, c):
    esiti.append(bool(c))
    print(('OK   ' if c else 'NO   ') + t, flush=True)


CHROME = 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900})
        err = []
        pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
        pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = "([m, a]) => fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)}).then(r => r.json())"
        aggiorna = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r; }")
        assert pg.evaluate(aggiorna, ['new_project', ['lamiera', {'name': 'Fianco', 'larghezza': 300, 'profondita': 200, 'spessore': 3,
                                                                 'raggio': 3, 'k': 0.33}]])['ok']
        assert pg.evaluate(aggiorna, ['save', [str(cart / 'Fianco.steelcad')]])['ok']
        time.sleep(0.8)

        def conferma(cmd, titolo, file, foto):
            pg.evaluate(f"window.__steelcad.runCmd('{cmd}')")
            pg.wait_for_selector('#fatto-apri', timeout=60000); time.sleep(0.4)
            t = pg.inner_text('#modal-box')
            ok(f'{cmd}: «{titolo}», il file {file} e la cartella', titolo in t and file in t and str(cart) in t
               and (cart / file).is_file())
            pg.screenshot(path=str(out / foto))
            pg.click('#fatto-apri'); time.sleep(0.3)
            ok(f'{cmd}: «Apri la cartella» senza errori, la conferma resta', not err and pg.is_visible('#fatto-apri'))
            pg.keyboard.press('Enter'); time.sleep(0.4)
            ok(f'{cmd}: Invio chiude', not pg.is_visible('#fatto-apri'))

        conferma('export_dxf', 'DXF di taglio salvato', 'Fianco.dxf', 'e1_dxf.png')
        conferma('export_step', 'STEP salvato', 'Fianco.step', 'e2_step.png')
        # tavole: «Esporta PDF» dall'editor
        pg.evaluate("window.__steelcad.runCmd('drawings')")
        pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(0.5)
        pg.click('#te-pdf')
        pg.wait_for_selector('#fatto-apri', timeout=60000); time.sleep(0.4)
        t = pg.inner_text('#modal-box')
        ok('tavole: «Tavole in PDF salvate», Fianco_tavole.pdf e la cartella',
           'Tavole in PDF salvate' in t and 'Fianco_tavole.pdf' in t and (cart / 'Fianco_tavole.pdf').is_file())
        pg.screenshot(path=str(out / 'e3_tavole_pdf.png'))
        pg.click('#m-ok'); time.sleep(0.4)
        ok('tavole: chiusa la conferma l’editor resta aperto', pg.is_visible('#tav-ed') and not pg.is_visible('#fatto-apri'))
        pg.click('#te-chiudi'); time.sleep(0.5)
        # assieme: la distinta in Excel
        r = pg.evaluate(aggiorna, ['new_assembly_con_pezzi', ['Telaio', [{'path': str(cart / 'Fianco.steelcad'), 'n': 2}]]])
        assert r['ok'], r
        assert pg.evaluate(aggiorna, ['save', [str(cart / 'Telaio.steelcad-asm')]])['ok']
        time.sleep(1)
        conferma('export_bom', 'Distinta in Excel salvata', 'Telaio_distinta.xlsx', 'e4_excel.png')
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
