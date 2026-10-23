"""Prova dell'interfaccia: pagina iniziale (Nuovo, recenti, ricerca), menu File con i sottomenu, nuovo assieme con le quantità,
impostazioni, lamiera che si apre subito (22/10).

    python tools/prova_ui_home.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5181', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1400, 'height': 850}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.add_init_script("try { localStorage.setItem('steelcad.tema', 'scuro'); } catch {}")
        pg.goto('http://127.0.0.1:5181/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000); time.sleep(1.5)
        pg.screenshot(path=str(OUT / '1_home_vuota.png'))
        pg.click('#top .menu-item >> nth=0'); time.sleep(0.5)
        chk('File nella home si vede', pg.is_visible('text=Nuovo assieme…'))
        pg.screenshot(path=str(OUT / '2_file_home.png'))
        pg.keyboard.press('Escape')
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        for nome, (w, d) in (('Fondo', (400, 300)), ('Parete A', (400, 150)), ('Parete B', (300, 150))):
            api('new_project', 'lamiera', {'name': nome, 'larghezza': w, 'profondita': d, 'spessore': 2})
            api('save', str(cart / f'{nome}.steelcad'))
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.3)
        pg.evaluate("window.__steelcad.runCmd('home')"); time.sleep(1)
        chk('3 lavori recenti', pg.locator('.home-rec').count() == 3)
        pg.fill('#home-cerca', 'parete'); time.sleep(0.2)
        chk('ricerca: 2', pg.locator('.home-rec').count() == 2)
        pg.fill('#home-cerca', '')
        pg.click('.home-nuovo[data-cat="struttura"]'); time.sleep(0.4)
        chk('Tubi apre la scelta', pg.is_visible('text=Che struttura in tubi?'))
        pg.screenshot(path=str(OUT / '3_home_tubi.png'))
        pg.click('[data-chiudi-tipi] >> visible=true')
        # nuovo assieme con quantità
        pg.click('.home-nuovo[data-new="assieme"]'); time.sleep(1)
        pg.fill('#n-name', 'Scatola')
        nomi = pg.evaluate("[...document.querySelectorAll('#na-tab b')].map(b => b.textContent)")
        for n in ('Fondo', 'Parete A', 'Parete B'):
            pg.fill(f'[data-n="{nomi.index(n)}"]', {'Fondo': '1', 'Parete A': '2', 'Parete B': '2'}[n])
        chk('base = Fondo', 'base' in pg.inner_text(f'#na-tab tr:nth-child({nomi.index("Fondo") + 1})'))
        chk('totale ' + pg.inner_text('#na-tot'), '5 in tutto' in pg.inner_text('#na-tot'))
        pg.screenshot(path=str(OUT / '4_nuovo_assieme.png'))
        pg.click('#n-ok'); time.sleep(4)
        st = api('state')
        ist = st.get('instances') or []
        chk(f'assieme con 5 copie, Fondo fermo: {[(i["name"], i["fixed"]) for i in ist]}', len(ist) == 5 and ist[0]['fixed'] and ist[0]['name'] == 'Fondo')
        pg.screenshot(path=str(OUT / '5_assieme.png'))
        # menu File con sottomenu
        pg.click('#top .menu-item >> nth=0'); time.sleep(0.8)
        pg.hover('text=Esporta'); time.sleep(0.3)
        pg.screenshot(path=str(OUT / '6_file_esporta.png'))
        pg.hover('text=Apri recenti'); time.sleep(0.3)
        chk('recenti nel menu', pg.locator('#m-recenti [data-recente]').count() >= 3)
        pg.screenshot(path=str(OUT / '7_file_recenti.png'))
        pg.keyboard.press('Escape')
        # impostazioni
        pg.evaluate("window.__steelcad.runCmd('impostazioni')"); time.sleep(1)
        chk('impostazioni', pg.is_visible('.imp-nav'))
        pg.screenshot(path=str(OUT / '8_imp.png'))
        pg.click('[data-sez="tavole"]'); time.sleep(0.5); pg.fill('#i-az', 'Officina Prova'); pg.click('[data-sez="aspetto"]'); pg.click('#i-tema [data-v="chiaro"]'); pg.click('#i-ok'); time.sleep(1)
        chk('cartiglio salvato', api('drawing_fields')['fields']['azienda'] == 'Officina Prova')
        chk('tema chiaro applicato e salvato', not pg.evaluate("document.body.classList.contains('dark')") and api('impostazioni')['tema'] == 'chiaro')
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        chk('dopo il riavvio resta chiaro', not pg.evaluate("document.body.classList.contains('dark')"))
        pg.evaluate("localStorage.clear()")
        pg.screenshot(path=str(OUT / '9_imp_tavole.png'))
        # lamiera diretta
        pg.evaluate("window.__steelcad.runCmd('home')"); time.sleep(1)
        pg.click('.home-nuovo[data-new="lamiera"]'); time.sleep(3)
        chk('lamiera aperta subito', pg.is_hidden('#home') and api('state').get('sheet') is not None)
        chk('riga del materiale', pg.is_visible('#mat-sel'))
        pg.select_option('#mat-sel', 'AISI304'); time.sleep(2)
        chk('materiale cambiato: ' + api('state')['materiale'], api('state')['materiale'] == 'AISI304')
        pg.screenshot(path=str(OUT / '10_lamiera.png'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
