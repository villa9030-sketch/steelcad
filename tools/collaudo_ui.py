"""Collaudo dell'interfaccia: in ogni situazione clicca TUTTI i pulsanti visibili e TUTTE le voci del menu comandi.

    python tools/collaudo_ui.py [cartella] --chrome

Per ogni clic riparte da uno stato pulito. Se si apre una finestra, conferma con i valori proposti (così il comando
viene eseguito davvero), poi chiude. Con gli strumenti di disegno fa due clic sul foglio. Annota:
  BUG       errore JavaScript, errore in console, messaggio "Errore interno";
  RIFIUTO   messaggio d'errore normale (da guardare: può essere giusto o un comando che non va dove dovrebbe).
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
PORTA = 5160
argv = [a for a in sys.argv[1:] if not a.startswith('--')]
OUT = Path(argv[0]) if argv else Path(tempfile.mkdtemp(prefix='collaudo_ui_'))
OUT.mkdir(parents=True, exist_ok=True)
CART = OUT / 'file'
CART.mkdir(exist_ok=True)
RIS = []

API = """async ([m, a]) => { const r = await (await fetch('/api/' + m, {method: 'POST', body: JSON.stringify(a)})).json();
  if (r && r.state) { await window.__steelcad.apply(r); window.__steelcad.hideHome(); } return r; }"""
LAM = {'name': 'Prova', 'larghezza': 200, 'profondita': 120, 'spessore': 2, 'raggio': 2, 'k': 0.4}


def scenario_lamiera(pg):
    pg.evaluate(API, ['new_project', ['lamiera', LAM]])
    pg.evaluate(API, ['add_flange', ['SM1', 'L1', {'length': '30'}]])


def scenario_flangia(pg):
    scenario_lamiera(pg)
    pg.click('#tree .node:has-text("Piega davanti")')       # FL1 sul lato sotto: nell'albero si chiama a parole


def scenario_sketch(pg):
    scenario_lamiera(pg)
    sid = pg.evaluate(API, ['sketch_on_face', ['SM1/sopra']])['sketch']
    pg.evaluate(API, ['sketch_add_rectangle', [sid, [40, 30], [120, 80]]])
    pg.evaluate(f"window.__steelcad.enterSketch('{sid}')")
    time.sleep(1)


def scenario_sketch_sel(pg):
    scenario_sketch(pg)
    pg.click('#ribbon [data-tool="select"]')
    pg.keyboard.press('Control+a')


def scenario_struttura(pg):
    pg.evaluate(API, ['new_project', ['telaio', {}]])


def scenario_asta(pg):
    scenario_struttura(pg)
    pg.click('#tree .node.leaf >> nth=0') if pg.locator('#tree .node.leaf').count() else None
    nodi = pg.locator('#tree .node')
    for i in range(nodi.count()):
        if '×' in nodi.nth(i).inner_text():
            nodi.nth(i).click()
            break


def scenario_cono(pg):
    pg.evaluate(API, ['new_project', ['cono', {}]])


def scenario_assieme(pg):
    pg.evaluate(API, ['new_project', ['lamiera', LAM]])
    pg.evaluate(API, ['save', [str(CART / 'pezzo.steelcad')]])
    pg.evaluate(API, ['new_assembly', ['Assieme']])
    pg.evaluate(API, ['asm_insert', [str(CART / 'pezzo.steelcad')]])
    pg.evaluate(API, ['asm_insert', [str(CART / 'pezzo.steelcad')]])


def scenario_home(pg):
    pg.click('#top .brand')
    pg.wait_for_selector('#home:not([hidden])')


SCENARI = [('lamiera', scenario_lamiera), ('flangia selezionata', scenario_flangia), ('sketch', scenario_sketch),
           ('sketch con selezione', scenario_sketch_sel), ('struttura', scenario_struttura), ('asta selezionata', scenario_asta),
           ('cono', scenario_cono), ('assieme', scenario_assieme), ('pagina iniziale', scenario_home)]

PULSANTI = ('#ribbon button:visible, #props button:visible, #sk-panel button:visible, #navbar button:visible, '
            '#home button:visible, #bottom button:visible, #flat-bar button:visible, #props summary:visible, #sk-panel summary:visible')


def annota(tipo, scen, cosa, det=''):
    RIS.append({'tipo': tipo, 'scenario': scen, 'cosa': cosa, 'dettaglio': str(det)[:500]})
    if tipo != 'OK':
        print(f'  {tipo:8} [{scen}] {cosa} → {str(det)[:200]}', flush=True)


def pronto(pg, err):
    pg.goto(f'http://127.0.0.1:{PORTA}/?dev')
    pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
    pg.evaluate("""() => { window.__msg = []; new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes)
        if (n.classList) window.__msg.push([n.className, n.textContent]); }).observe(document.querySelector('#toasts'), {childList: true}); }""")
    err.clear()


def chiudi_tutto(pg):
    for _ in range(3):
        if pg.locator('#modal:not([hidden])').count():
            pg.keyboard.press('Escape')
            time.sleep(0.2)
            if pg.locator('#modal:not([hidden]) #m-no').count():
                pg.click('#modal:not([hidden]) #m-no')
        if pg.locator('#palette:not([hidden])').count():
            pg.keyboard.press('Escape')
        time.sleep(0.2)


def esito(pg, err, scen, cosa):
    time.sleep(1.2)
    msgs = pg.evaluate('window.__msg || []')
    bug = [e for e in err] + [t for c, t in msgs if 'Errore interno' in t]
    if bug:
        annota('BUG', scen, cosa, ' | '.join(bug))
    elif any('err' in c for c, _ in msgs):
        annota('RIFIUTO', scen, cosa, ' | '.join(t for c, t in msgs if 'err' in c))
    else:
        annota('OK', scen, cosa)


def prova_clic(pg, err, scen, setup, descr, azione):
    try:
        pronto(pg, err)
        setup(pg)
        time.sleep(0.6)
        pg.evaluate('window.__msg = []')
        err.clear()
        azione()
        time.sleep(0.8)
        # finestra: conferma con i valori proposti
        if pg.locator('#modal:not([hidden])').count():
            prim = pg.locator('#modal:not([hidden]) .btn.primary:visible')
            if prim.count():
                try:
                    prim.first.click(timeout=3000)
                    time.sleep(1.5)
                except Exception:  # noqa: BLE001
                    pass
        # strumento di disegno: due clic sul foglio
        if pg.evaluate('!!window.__steelcad.sketch && window.__steelcad.sketch.tool && !["select"].includes(window.__steelcad.sketch.tool)'):
            box = pg.locator('#c3d').bounding_box()
            if box:
                cx, cy = box['x'] + box['width'] * 0.45, box['y'] + box['height'] * 0.45
                pg.mouse.click(cx, cy)
                pg.mouse.click(cx + 60, cy + 40)
                pg.mouse.click(cx + 60, cy + 40)
        esito(pg, err, scen, descr)
        chiudi_tutto(pg)
    except Exception as ex:  # noqa: BLE001
        msg = str(ex).splitlines()[0][:200]
        annota('BUG' if err else 'NONPROVATO', scen, descr, ' | '.join(err) or msg)


def main():
    srv = subprocess.Popen([str(PY), str(ROOT / 'app' / 'dev_server.py'), '--porta', str(PORTA), '--cartella', str(CART)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                           env={**__import__('os').environ, 'STEELCAD_HOME': str(OUT / 'home'), 'STEELCAD_RULES': str(OUT / 'regole.json')})
    while not srv.stdout.readline().startswith(b'http'):
        pass
    t0 = time.time()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel='chrome' if '--chrome' in sys.argv else None,
                                  args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            pg = b.new_page(viewport={'width': 1440, 'height': 900})
            err = []
            pg.on('pageerror', lambda e: err.append('JS: ' + str(e)))
            pg.on('console', lambda m: err.append('console: ' + m.text) if m.type == 'error' else None)
            pg.on('dialog', lambda d: d.dismiss())
            for scen, setup in SCENARI:
                print(f'\n=== {scen}', flush=True)
                pronto(pg, err)
                setup(pg)
                time.sleep(0.8)
                if err:
                    annota('BUG', scen, 'preparazione', ' | '.join(err))
                # i pulsanti visibili in questa situazione (per testo e posizione)
                elenco = pg.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(b => b.offsetParent && !b.disabled)
                    .map((b, i) => ({i, t: (b.innerText || b.title || b.id || '').trim().replace(/\\s+/g, ' ').slice(0, 40)}))""", PULSANTI.replace(':visible', ''))
                pg.screenshot(path=str(OUT / f'{scen}.png'))
                print(f'    {len(elenco)} pulsanti', flush=True)
                for it in elenco:
                    if it['t'] in ('', 'Chiudi', '×'):
                        continue
                    i = it['i']
                    prova_clic(pg, err, scen, setup, f'pulsante «{it["t"]}»',
                               lambda i=i: pg.evaluate("""([sel, i]) => [...document.querySelectorAll(sel)]
                                   .filter(b => b.offsetParent && !b.disabled)[i].click()""", [PULSANTI.replace(':visible', ''), i]))
                # menu comandi
                pronto(pg, err)
                setup(pg)
                pg.keyboard.press('Control+k')
                time.sleep(0.4)
                voci = pg.evaluate("[...document.querySelectorAll('#pal-list li')].map(l => l.firstChild.textContent.trim())")
                pg.keyboard.press('Escape')
                print(f'    {len(voci)} voci nel menu comandi', flush=True)
                if scen in ('sketch con selezione', 'flangia selezionata', 'asta selezionata'):
                    continue                     # il menu è lo stesso delle situazioni base
                for k, v in enumerate(voci):
                    def apri(k=k):
                        pg.keyboard.press('Control+k')
                        time.sleep(0.3)
                        pg.click(f'#pal-list li[data-i="{k}"]')
                    prova_clic(pg, err, scen, setup, f'menu «{v}»', apri)
            b.close()
    finally:
        srv.kill()
    conta = {}
    for r in RIS:
        conta[r['tipo']] = conta.get(r['tipo'], 0) + 1
    (OUT / 'rapporto_ui.json').write_text(json.dumps(RIS, indent=1), encoding='utf-8')
    print(f'\n{len(RIS)} prove in {time.time() - t0:.0f} s — ' + ', '.join(f'{k}: {v}' for k, v in sorted(conta.items())))


if __name__ == '__main__':
    main()
