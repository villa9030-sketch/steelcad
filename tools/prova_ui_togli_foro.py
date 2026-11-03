"""Prova dell'interfaccia: un foro cliccato sul pezzo (vista 3D) si toglie da lì (28/10) — pulsante «Togli questo
foro» o Canc; gli altri fori dello stesso taglio restano; l'ultimo toglie il taglio intero (una conferma sola). E i nomi
dei tagli nell'albero dicono cosa c'è.

    python tools/prova_ui_togli_foro.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5205', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5205/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'P', 'larghezza': 300, 'profondita': 200, 'spessore': 2, 'raggio': 2, 'k': 0.4})
        sid = api('sketch_on_face', 'SM1/sopra')['sketch']
        for x in (50, 150, 250): api('sketch_add_circle', sid, [x, 100], 10)
        api('create_from_sketch', sid, 'cut', {})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        pg.evaluate("window.__steelcad.hideHome()"); time.sleep(0.5)
        albero = pg.inner_text('#tree')
        chk('nell’albero il taglio si chiama «Fori 3 × Ø20»', 'Fori 3 × Ø20' in albero)

        def pareti():
            return pg.evaluate("(() => { const o = window.__steelcad.objs.get('body'); return o.data.faces.filter(f => (f.name || '').startsWith('TG1/parete')).map(f => f.index); })()")
        idx = pareti()
        chk(f'pareti dei fori nel 3D: {len(idx)}', len(idx) >= 3)
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        # 03/11: il clic sul foro apre la sua scheda (barretta) col cestino «Togli il foro»
        TOGLI = '#mini-barra [data-a="togli"]'
        pg.wait_for_selector(TOGLI, timeout=10000)
        chk('scheda del foro con «Togli il foro»', pg.is_visible(TOGLI))
        pg.screenshot(path=str(OUT / '1_pannello.png'))
        pg.wait_for_selector(TOGLI, timeout=10000); pg.click(TOGLI)
        # 03/11: la conferma in basso («Toglie il foro: la lamiera torna piena»), Invio
        pg.wait_for_selector('#pr-ok', timeout=10000); BARRA = 'body'
        chk('chiede conferma in basso', 'Toglie' in pg.inner_text(BARRA))
        pg.click('#pr-ok'); time.sleep(2.5)
        st = api('state')
        chk('tolto un foro: «Fori 2 × Ø20»', 'Fori 2 × Ø20' in str(st['tree']))
        # Canc su un altro
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        idx = pareti()
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        pg.mouse.move(800, 450); pg.keyboard.press('Delete')
        # 03/11: Invio subito, mentre l'anteprima si calcola ancora: dice «Sto calcolando…» e poi lo fa
        pg.wait_for_selector('#prova-barra', timeout=10000)
        pg.keyboard.press('Enter')
        scritta = pg.inner_text('#prova-barra') if pg.locator('#prova-barra').count() else ''
        print('   barra dopo Invio subito:', repr(scritta[:120]), flush=True)
        pg.screenshot(path=str(OUT / '1b_invio_subito.png'))
        for _ in range(40):                                # sotto carico il ricalcolo può metterci qualche secondo
            st = api('state')
            if '2 ×' not in str(st['tree']):
                break
            time.sleep(0.5)
        chk('Canc: ne resta uno, «Foro Ø20»', 'Foro Ø20' in str(st['tree']) and '2 ×' not in str(st['tree']))
        # l'ultimo: chiede di togliere il taglio
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5); pg.evaluate("window.__steelcad.hideHome()")
        idx = pareti()
        pg.evaluate("i => window.__steelcad.select('body', i)", idx[0]); time.sleep(1.2)
        pg.wait_for_selector(TOGLI, timeout=10000); pg.click(TOGLI)
        pg.wait_for_selector('#pr-ok', timeout=10000); time.sleep(1)
        pg.wait_for_selector('#pr-ok:not([disabled])', timeout=10000)
        chk(f'l’ultimo: chiede di togliere il taglio intero ({pg.inner_text("#prova-barra")[:90]!r})', 'unico' in pg.inner_text('#prova-barra'))
        pg.screenshot(path=str(OUT / '2_ultimo.png'))
        pg.click('#pr-ok')
        # 03/11: una conferma sola: niente più la finestra «Elimina» dopo la barra
        time.sleep(1.5)
        chk('… e nessuna seconda conferma (finestra «Elimina»)', pg.locator('#modal:not([hidden])').count() == 0)
        pg.screenshot(path=str(OUT / '3_tolto.png'))
        for _ in range(40):                                # aspetta il ricalcolo (sotto carico qualche secondo)
            if "'sheet_cut'" not in str(api('state')['tree']):
                break
            time.sleep(0.5)
        albero = api('state')['tree']
        chk('taglio tolto', "'sheet_cut'" not in str(albero))
        if "'sheet_cut'" in str(albero): print('   albero:', albero)
        api('undo'); api('undo'); api('undo')
        chk('Annulla rimette i tre fori', 'Fori 3 × Ø20' in str(api('state')['tree']))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
