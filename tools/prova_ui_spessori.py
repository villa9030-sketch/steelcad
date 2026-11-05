"""Prova dell'interfaccia degli spessori preferiti (05/11, regole personali come in SolidCraft) nel browser senza
finestra. Due regole salvate («Inox 2», «Ferro 3 V24»): lamiera nuova → a sinistra la tendina «Regola» → scelgo Inox 2
e il pezzo prende materiale, spessore, raggio e K; nella scheda Lamiera in basso cambio in Ferro 3; Annulla torna
indietro; rinomino la regola (il pezzo non cambia); la cancello (il pezzo resta Inox); la staffa pronta con la regola;
lo STEP prende il K dalla regola; tema scuro.

    python tools/prova_ui_spessori.py [cartella_screenshot] [porta]
"""
import json
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
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5306
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cart = tmp / 'lavori'
cart.mkdir()
# le regole personali stanno nei Documenti dell'utente (qui: la cartella finta)
regole = tmp / 'Documents' / 'SteelCAD' / 'regole_lamiera.json'
regole.parent.mkdir(parents=True)
regole.write_text(json.dumps({'format': 'steelcad-regole', 'rules': [
    {'name': 'Ferro 3 V24', 'material': 'S235', 'thickness': 3, 'radius': 4, 'method': 'k', 'k': 0.45, 'bd90': None},
    {'name': 'Inox 2', 'material': 'AISI304', 'thickness': 2, 'radius': 2, 'method': 'k', 'k': 0.4, 'bd90': None}],
    'default': {'radius': 1, 'k': 0.33, 'method': 'k'}}), encoding='utf-8')
env = {**os.environ, 'STEELCAD_HOME': str(tmp / '.sc'), 'USERPROFILE': str(tmp)}
env.pop('STEELCAD_RULES', None)
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
        applica = ("async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();"
                   " await window.__steelcad.apply(r); window.__steelcad.hideHome(); return r.ok || r.message; }")
        st = lambda espr: pg.evaluate(f'(() => {{ const S = window.__steelcad.state; return {espr}; }})()')  # noqa: E731
        sp = lambda: st("S.parameters.find(p => p.name === 'sp').value")  # noqa: E731

        assert pg.evaluate(applica, ['new_project', ['lamiera', {'name': 'Lamiera', 'larghezza': 500, 'profondita': 300, 'spessore': 2}]]) is True
        assert pg.evaluate(applica, ['add_flange', ['SM1', 'L1', {'length': '40'}]]) is True
        time.sleep(1.0)
        ok('a sinistra la tendina «Regola» sopra raggio e K', pg.is_visible('#regola-sx'))
        ok('il pezzo coi valori del predefinito non è una regola', pg.input_value('#regola-sx') == '')
        testi = pg.eval_on_selector_all('#regola-sx option', 'os => os.map(o => o.textContent)')
        ok(f'le regole con le parole: {testi}', any('Inox 2 (Inox 304 sp. 2 · R 2 · K 0,4)' == t for t in testi))
        pg.screenshot(path=str(out / 'sp1_tendina.png'))

        # scelgo Inox 2: materiale, spessore, raggio, K in un colpo
        pg.select_option('#regola-sx', 'Inox 2')
        pg.wait_for_function("window.__steelcad.state.sheet.regola === 'Inox 2'", timeout=15000)
        time.sleep(0.6)
        ok('materiale Inox 304', st('S.materiale') == 'AISI304')
        ok('spessore 2, raggio 2, K 0,4', sp() == 2 and st('S.sheet.def.radius') == 2 and st('S.sheet.def.k') == 0.4)
        ok('la tendina ora dice Inox 2', pg.input_value('#regola-sx') == 'Inox 2')
        ok('il materiale a sinistra segue', pg.input_value('#mat-sel') == 'AISI304')
        pg.screenshot(path=str(out / 'sp2_inox.png'))

        # scheda Lamiera in basso: cambio in Ferro 3
        pg.evaluate("window.__prova.showTab('sheet', true)"); time.sleep(0.5)
        ok('nella scheda Lamiera la stessa scelta', pg.is_visible('#regola-sh') and pg.input_value('#regola-sh') == 'Inox 2')
        pg.select_option('#regola-sh', 'Ferro 3 V24')
        pg.wait_for_function("window.__steelcad.state.sheet.regola === 'Ferro 3 V24'", timeout=15000)
        time.sleep(0.6)
        ok('spessore 3, raggio 4, ferro', sp() == 3 and st('S.sheet.def.radius') == 4 and st('S.materiale') == 'S235')
        pg.screenshot(path=str(out / 'sp3_scheda_ferro.png'))
        pg.keyboard.press('Control+z')
        pg.wait_for_function("window.__steelcad.state.sheet.regola === 'Inox 2'", timeout=15000)
        ok('Annulla: un passo solo, torna Inox 2', sp() == 2 and st('S.materiale') == 'AISI304')

        # «Salva o cambia le regole…» apre la finestra; rinomina sul posto
        pg.select_option('#regola-sx', '__gestisci')
        pg.wait_for_selector('#modal-box [data-rule-ren]', timeout=10000)
        ok('la tendina non resta su «Salva o cambia…»', pg.input_value('#regola-sx') == 'Inox 2')
        ok('nella finestra si vede quale è del pezzo', 'è quella di questo pezzo' in pg.inner_text('#modal-box'))
        pg.click('#modal-box [data-rule-ren="Inox 2"]')
        pg.fill('#modal-box .rinomina-regola input', 'Inox 304 sp. 2')
        pg.screenshot(path=str(out / 'sp4_rinomina.png'))
        pg.keyboard.press('Enter')
        pg.wait_for_selector('#modal-box [data-rule-ren="Inox 304 sp. 2"]', timeout=10000)
        time.sleep(0.4)
        ok('rinominata nel file', [r['name'] for r in json.loads(regole.read_text(encoding='utf-8'))['rules']] == ['Ferro 3 V24', 'Inox 304 sp. 2'])
        ok('il pezzo non cambia e la tendina ha il nome nuovo', pg.input_value('#regola-sx') == 'Inox 304 sp. 2' and sp() == 2)
        # salvare con un nome che c'è: chiede prima
        pg.fill('#r-name', 'Ferro 3 V24'); pg.click('#r-save'); time.sleep(0.4)
        ok('stesso nome: chiede prima di sostituire', pg.inner_text('#r-save') == 'Sì, sostituisci la regola'
           and json.loads(regole.read_text(encoding='utf-8'))['rules'][0]['thickness'] == 3)
        pg.screenshot(path=str(out / 'sp5_sostituisci.png'))
        # cancello la regola del pezzo: il pezzo resta com'è
        pg.click('#modal-box [data-rule-del="Inox 304 sp. 2"]')
        pg.wait_for_function("!document.querySelector('#modal-box [data-rule-del=\"Inox 304 sp. 2\"]')", timeout=10000)
        time.sleep(0.4)
        pg.click('#m-no'); time.sleep(0.3)
        ok('cancellata: il pezzo resta inox sp. 2 R 2 K 0,4', st('S.materiale') == 'AISI304' and sp() == 2 and st('S.sheet.def.k') == 0.4)
        ok('la tendina torna su «valori di questo pezzo»', pg.input_value('#regola-sx') == '')

        # pezzo pronto: la staffa con la regola
        pg.evaluate("window.__prova.modello('staffa')"); time.sleep(0.5)
        ok('nella staffa la scelta della regola', pg.is_visible('#mod-regola'))
        pg.select_option('#mod-regola', 'Ferro 3 V24'); time.sleep(0.3)
        ok('spessore, raggio e K riempiti', pg.input_value('.mod-campi input[data-k="spessore"]') == '3'
           and pg.input_value('#mod-r') == '4' and pg.input_value('#mod-k') == '0,45')
        pg.screenshot(path=str(out / 'sp6_staffa.png'))
        pg.click('#m-ok')
        pg.wait_for_function("window.__steelcad.state.name === 'Staffa a L' && window.__steelcad.state.sheet", timeout=20000)
        time.sleep(0.8)
        ok('la staffa è Ferro 3 V24', st('S.sheet.regola') == 'Ferro 3 V24' and st('S.sheet.flanges') == 1)

        # STEP: la regola dà il K
        pg.evaluate("window.__prova.stepDialog()"); time.sleep(0.4)
        pg.select_option('#st-regola', 'Ferro 3 V24'); time.sleep(0.2)
        ok('STEP: il K dalla regola', pg.input_value('#st-k') == '0,45')
        pg.screenshot(path=str(out / 'sp7_step.png'))
        pg.click('#m-no'); time.sleep(0.3)

        # tema scuro
        pg.evaluate("window.__prova.applyTheme(true)"); time.sleep(0.5)
        pg.screenshot(path=str(out / 'sp8_scuro.png'))
        pg.evaluate("window.__prova.applyTheme(false)")
        ok('nessun errore nella pagina', not err)
        if err:
            print(err)
        b.close()
finally:
    srv.kill()
print(f'{sum(esiti)}/{len(esiti)} ok')
sys.exit(0 if all(esiti) else 1)
