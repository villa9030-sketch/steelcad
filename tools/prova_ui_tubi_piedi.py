r"""Strutture in tubo, secondo giro (03/11): Dividi propone il lato cliccato e lo accende, i disegnini dell'incrocio,
piedi e tappi dalla barra con l'anteprima, la distinta di taglio coi piedi e i tappi. Una foto per passo.

    .venv\Scripts\python.exe tools\prova_ui_tubi_piedi.py cartella_foto [porta]
"""
import os, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from ui_barra import comando, comando_visibile, scheda, chiudi_cassetto, pannello_intero  # noqa: F401  (comandi della barra, anche in «Altro ▾»)
ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
SP.mkdir(parents=True, exist_ok=True)
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5268
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(PY), str(ROOT / 'app/dev_server.py'), '--porta', str(PORTA), '--cartella', str(cart)], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000,
                       env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
n = [0]
ok_tutti = []


def foto(cosa):
    n[0] += 1
    print(f'FOTO {n[0]:02d} {cosa}', flush=True)
    time.sleep(0.4)
    pg.screenshot(path=str(SP / f'{n[0]:02d}.png'))


def ok(cosa, v):
    ok_tutti.append(bool(v))
    print(('OK  ' if v else 'NO  ') + cosa, flush=True)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe', args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []
        pg.on('pageerror', lambda e: err.append(str(e))); pg.on('console', lambda m: m.type == 'error' and err.append(m.text + ' ' + str(m.location)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
        api = lambda nm, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [nm, list(a)])
        time.sleep(1)
        pg.evaluate("window.__steelcad.nuovo('telaio')"); time.sleep(1)
        for k, v in (('L', '807'), ('P', '725'), ('H', '795'), ('ripiano', '0'), ('profilo', '30x30x2'), ('gambe', '30x30x2')):
            pg.fill(f'[data-f="{k}"]', v)
        pg.click('#n-ok'); time.sleep(4)

        def clic_punto(xyz):
            xy = pg.evaluate("p => window.__steelcad.toScreen(p)", xyz)
            box = pg.locator('#c3d').bounding_box()
            pg.mouse.move(box['x'] + xy[0], box['y'] + xy[1]); time.sleep(0.3)
            pg.mouse.click(box['x'] + xy[0], box['y'] + xy[1]); time.sleep(1.8)

        # 1. Dividi: clic sul DAVANTI del tubo davanti in alto → propone il davanti, acceso nel 3D
        comando(pg, '.rb[data-azione="dividi"]'); time.sleep(0.5)
        clic_punto([400, 0, 775]); time.sleep(1.5)
        ok('clic sul davanti del tubo: proposto «Il davanti»', 'on' in (pg.get_attribute('[data-dvf="davanti"]', 'class') or ''))
        foto('Dividi: clic sul davanti del tubo in alto → «Il davanti» acceso')
        pg.click('#dv-no'); time.sleep(1)
        box = pg.locator('#c3d').bounding_box()
        pg.mouse.click(box['x'] + 40, box['y'] + 40); time.sleep(1)       # clic nel vuoto: niente scelto
        # clic sul SOPRA dello stesso tubo → il telaio sopra
        comando(pg, '.rb[data-azione="dividi"]'); time.sleep(0.5)
        clic_punto([400, 15, 795]); time.sleep(1.5)
        ok('clic sul sopra del tubo: proposto «Il telaio sopra»', 'on' in (pg.get_attribute('[data-dvf="sopra"]', 'class') or ''))
        foto('Dividi: clic sul sopra del tubo → «Il telaio sopra» acceso')
        pg.click('#dv-ok'); time.sleep(3)
        # 2. l'incrocio della croce: due disegnini diversi
        nodo = pg.evaluate("window.__steelcad.nodes.find(n => n.key.includes('×')).id")
        pg.evaluate("id => window.__steelcad.select(id)", nodo); time.sleep(1.5)
        disegni = pg.evaluate("[...document.querySelectorAll('[data-angolo] svg')].map(s => s.innerHTML)")
        ok('incrocio: due disegnini diversi', len(disegni) == 2 and disegni[0] != disegni[1])
        foto('Incrocio: chi passa intero, col disegnino')
        pg.locator('.angoli').screenshot(path=str(SP / 'incrocio_disegnini.png'))
        # 3. Piedi dalla barra: anteprima, poi Metti
        pg.evaluate("window.__steelcad.select('struct=ST1')"); time.sleep(1)
        comando(pg, '.rb[data-azione="piedi"]'); time.sleep(2.5)
        ok('pannello piedi aperto', pg.is_visible('#pd-ok'))
        foto('Piedi: piastra 80×80 sp. 6, 4 fori, anteprima')
        pg.click('[data-pd-tipo="piedino"]'); time.sleep(2.5)
        foto('Piedi: piedino regolabile M10, anteprima')
        pg.click('[data-pd-tipo="piastra"]'); time.sleep(2)
        pg.click('#pd-ok'); time.sleep(3)
        st = api('state')
        acc = (st.get('cutlist') or {}).get('accessori') or []
        ok('4 piastre in distinta', any(a['qty'] == 4 and a['description'].startswith('Piastra 80×80') for a in acc))
        foto('Piedi messi')
        # 4. Tappi
        comando(pg, '.rb[data-azione="tappi"]'); time.sleep(2.5)
        foto('Tappi: anteprima sulle teste aperte')
        pg.click('#pd-ok'); time.sleep(3)
        st = api('state')
        acc = (st.get('cutlist') or {}).get('accessori') or []
        ok('4 tappi in plastica in distinta', any(a['qty'] == 4 and a['acquisto'] for a in acc))
        # 5. distinta di taglio aperta
        scheda(pg, 'cut'); time.sleep(0.5)
        if pg.is_visible('#bottom-toggle') and 'bottom-closed' in (pg.get_attribute('body', 'class') or ''):
            pg.click('#bottom-toggle'); time.sleep(0.8)
        pg.evaluate("document.querySelector('#tab-cut h4')?.scrollIntoView()"); time.sleep(0.5)
        foto('Distinta di taglio con piedi e tappi')
        # 6. clic su una piastra nel 3D: il pannello dei piedi (04/11: cassetto chiuso, aperto è alto quanto le righe
        # e la vista si accorcia: la piastra diventa piccola e il clic prende il pallino del capo della gamba)
        chiudi_cassetto(pg); time.sleep(1.5)
        clic_punto([-18, -18, -3]); time.sleep(1.5)
        ok('clic sulla piastra: pannello Piedi', pg.is_visible('#pd-ok'))
        foto('Clic su una piastra')
        # 7. tubo rettangolare: come sta, col disegnino della sezione
        r = api('new_project', 'telaio', {'L': 1000, 'P': 600, 'H': 800, 'ripiano': 0, 'profilo': '40x20x2', 'gambe': '40x40x3'})
        pg.evaluate("r => window.__steelcad.apply(r)", r); time.sleep(3)
        # notte 03/11: il clic sul tubo dà la barretta; «⋯» apre il pannello intero (come la lamiera)
        clic_punto([500, 0, 780]); pannello_intero(pg, '[data-posiz]')
        pg.locator('[data-posiz="1"]').scroll_into_view_if_needed(); time.sleep(0.5)
        ok('tubo rettangolare: due posizioni col disegnino', pg.locator('[data-posiz]').count() == 2)
        foto('Traverso 40×20: come sta il profilo (in piedi / sdraiato)')
        bb = pg.locator('[data-posiz="1"]').bounding_box()
        pg.mouse.move(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2); time.sleep(2.5)
        foto('passando su «Sdraiato»: anteprima')
        pg.mouse.click(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2); time.sleep(3)
        pg.wait_for_selector('[data-posiz]', timeout=10000); time.sleep(0.5)
        ok('girato: ora «Sdraiato» è scelto', 'on' in (pg.get_attribute('[data-posiz="1"]', 'class') or ''))
        foto('Sdraiato (anche gli altri del gruppo)')
        r = api('new_project', 'telaio', {'L': 1000, 'P': 600, 'H': 800, 'ripiano': 0, 'profilo': 'L 40x40x4', 'gambe': '40x40x3'})
        pg.evaluate("r => window.__steelcad.apply(r)", r); time.sleep(3)
        clic_punto([500, 0, 798]); pannello_intero(pg, '[data-posiz]')
        pg.locator('[data-posiz="1"]').scroll_into_view_if_needed(); time.sleep(0.5)
        ok('angolare: quattro posizioni', pg.locator('[data-posiz]').count() == 4)
        foto('Angolare: dove sta lo spigolo')
        # 8. cancello 60×40: la cut list col pezzo disegnato (45° a trapezio, angolo sul lato da 60) e Prepara
        r = api('new_project', 'cancello', {'L': 1500, 'H': 1200, 'telaio': '60x40x3', 'sbarre': '20x20x2', 'passo': 120})
        pg.evaluate("r => window.__steelcad.apply(r)", r); time.sleep(3)
        scheda(pg, 'cut'); time.sleep(0.8)
        testo = pg.inner_text('#tab-cut')
        ok('cut list: «45° / 45° a trapezio, angolo sul lato da 60»', '45° / 45° a trapezio, angolo sul lato da 60' in testo)
        ok('cut list: il pezzo disegnato', pg.locator('#tab-cut svg.forma-pezzo').count() == 2)
        foto('Cut list del cancello: tagli a 45° disegnati e scritti')
        pg.click('#b-prepara'); time.sleep(2.5)
        ok('Prepara: la lista per la troncatrice o il laser tubo', 'troncatrice o il laser tubo' in pg.inner_text('body'))
        ok('Prepara: una voce sola per la troncatrice, in Excel (niente CSV a parte)',
           pg.inner_text('body').count('troncatrice') == 1 and '_taglio.xlsx' in pg.inner_text('body')
           and '_taglio_tubi.csv' not in pg.inner_text('body'))
        foto('Prepara per l’officina: la lista dei tubi')
        print('errori', err)
        ok('nessun errore nella pagina', not err)
        b.close()
finally:
    srv.kill()
print('TUTTO OK' if all(ok_tutti) else 'QUALCOSA NON VA')
