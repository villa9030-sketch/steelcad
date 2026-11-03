"""Prova dell'interfaccia: il nome del pezzo in alto (03/11). Solo il nome (il percorso nel suggerimento), clic = campo,
Invio = nome nuovo; il primo «Salva» di un pezzo nuovo chiede come si chiama.

    python tools/prova_ui_nome_pezzo.py [cartella_screenshot] [porta]
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
        aggiorna = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                    " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r; }")
        assert pg.evaluate(aggiorna, ['new_project', ['lamiera', {'larghezza': 300, 'profondita': 200, 'spessore': 3}]])['ok']
        time.sleep(0.8)
        ok('pezzo nuovo: in alto «Lamiera — non salvato»', pg.inner_text('#docname').strip() == 'Lamiera — non salvato')
        # primo Salva: chiede il nome, con quello che ha già selezionato
        pg.click('#top button.tbtn[data-cmd="save"]')
        pg.wait_for_selector('#sv-nome', timeout=5000); time.sleep(0.3)
        ok('primo Salva: chiede come si chiama, col nome pronto da riscrivere',
           pg.input_value('#sv-nome') == 'Lamiera' and pg.evaluate("document.activeElement.id") == 'sv-nome')
        pg.keyboard.type('Piastra base')
        pg.screenshot(path=str(out / 'n1_primo_salva.png'))
        pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.path && !window.__steelcad.state.dirty", timeout=15000); time.sleep(0.5)
        ok('salvato come «Piastra base.steelcad»', (cart / 'Piastra base.steelcad').is_file())
        ok('in alto solo il nome, il percorso nel suggerimento',
           pg.inner_text('#docname').strip() == 'Piastra base' and str(cart) in pg.get_attribute('#docname', 'title'))
        pg.mouse.move(5, 895)
        pg.screenshot(path=str(out / 'n2_salvato.png'))
        # clic sul nome: campo, scrivo, Invio
        pg.click('#docname'); pg.wait_for_selector('#doc-nome', timeout=3000)
        ok('clic sul nome: il campo col nome selezionato', pg.evaluate("document.activeElement.id") == 'doc-nome')
        pg.keyboard.type('Fianco destro')
        pg.screenshot(path=str(out / 'n3_scrive.png'))
        pg.keyboard.press('Enter')
        pg.wait_for_function("window.__steelcad.state.name === 'Fianco destro'", timeout=10000); time.sleep(0.5)
        ok('Invio: il pezzo si chiama «Fianco destro» (da salvare)',
           'Fianco destro' in pg.inner_text('#docname') and pg.evaluate('window.__steelcad.state.dirty'))
        ok('… anche nell’albero', 'Fianco destro' in pg.inner_text('#tree'))
        pg.screenshot(path=str(out / 'n4_rinominato.png'))
        # Esc lascia stare
        pg.click('#docname'); pg.wait_for_selector('#doc-nome'); pg.keyboard.type('Pippo'); pg.keyboard.press('Escape'); time.sleep(0.5)
        ok('Esc: il nome resta quello', pg.evaluate('window.__steelcad.state.name') == 'Fianco destro')
        # Ctrl+S salva il nome nel file (senza chiedere: è già salvato)
        pg.keyboard.press('Control+s'); pg.wait_for_function("!window.__steelcad.state.dirty", timeout=10000)
        ok('niente finestra al secondo Salva', not pg.is_visible('#sv-nome'))
        ok('nessun errore in pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok   foto in {out}')
