"""Prova dell'interfaccia: l'editor delle tavole (23/10) — sposti una vista, cambi il testo di una quota, ne aggiungi
una, metti una nota, testi più grandi, campi e logo nel cartiglio; Annulla e «Rimetti automatico».

    python tools/prova_ui_tavole.py [cartella]
"""
import os, subprocess, tempfile, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(r'C:\Users\Stefano\Documents\Vs code\steelcad'); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()); OUT.mkdir(exist_ok=True)
cart = Path(tempfile.mkdtemp())
from PIL import Image  # noqa: E402
Image.new('RGB', (300, 120), (200, 40, 40)).save(cart / 'logo.png')
srv = subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'app/dev_server.py'), '--porta', '5187', '--cartella', str(cart)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000, env=dict(os.environ, STEELCAD_HOME=str(cart / '.sc'), USERPROFILE=str(cart)))
while not srv.stdout.readline().startswith(b'http'): pass
ok = []
def chk(c, e): ok.append(bool(e)); print(('OK  ' if e else 'NO  ') + c, flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []; pg.on('pageerror', lambda e: err.append(str(e)))
        pg.goto('http://127.0.0.1:5187/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=30000)
        api = lambda n, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [n, list(a)])
        api('new_project', 'lamiera', {'name': 'Cassa', 'larghezza': 420, 'profondita': 260, 'spessore': 2})
        sidc = api('sketch_on_face', 'SM1/sopra')['sketch']; api('sketch_add_circle', sidc, [300, 130], 20); api('create_from_sketch', sidc, 'cut', {})
        pg.reload(); pg.wait_for_function('window.__steelcad && window.__steelcad.ready'); time.sleep(1.5)
        if pg.is_visible('#home-close'): pg.click('#home-close'); time.sleep(0.4)
        # il logo dalle Impostazioni
        pg.evaluate("window.__steelcad.runCmd('impostazioni')"); time.sleep(0.8)
        pg.click('[data-sez="tavole"]'); pg.click('#i-logo-sc'); time.sleep(0.8)
        chk('logo scelto: ' + pg.inner_text('#i-logo'), pg.inner_text('#i-logo').startswith('logo'))
        pg.screenshot(path=str(OUT / '0_impostazioni_logo.png'))
        pg.click('#m-no'); time.sleep(0.3)
        # l'editor
        pg.evaluate("window.__steelcad.runCmd('drawings')")
        pg.wait_for_selector('#tav-ed #te-foglio svg', timeout=60000); time.sleep(0.5)
        chk('editor aperto a tutto schermo', pg.is_visible('#tav-ed'))
        chk('logo nel cartiglio', pg.locator('#te-foglio svg image').count() >= 1)
        pg.screenshot(path=str(OUT / '1_editor.png'))
        ogg = pg.evaluate("[...document.querySelectorAll('#te-foglio [data-el]')].map(e => e.getAttribute('data-el'))")
        viste = sorted({t.split('/')[0] for t in ogg if t.startswith('vista:')})
        chk('viste cliccabili ' + str(viste), 'vista:alto' in viste or 'vista:fronte' in viste)
        # trascina una vista
        v = 'vista:alto' if 'vista:alto' in viste else viste[0]
        bb = pg.locator(f'#te-foglio [data-el="{v}"]').first.bounding_box()
        x, y = bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2
        pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + 40, y + 30, steps=6); pg.mouse.up(); time.sleep(1.5)
        r = api('drawing_preview', None)['sheets'][0]['ritocchi']
        chk('vista spostata e salvata ' + str(r.get('viste')), v in (r.get('viste') or {}))
        chk('elenco ritocchi: ' + pg.inner_text('#te-rit')[:60], 'spostata' in pg.inner_text('#te-rit'))
        # clic su una quota: testo nuovo
        q = next(t for t in ogg if '/q' in t)
        pg.locator(f'#te-foglio [data-el="{q}"]').first.click(force=True); time.sleep(0.4)
        chk('pannello della quota', pg.is_visible('#te-sel') and pg.is_visible('#ts-testo'))
        chk('campo Frecce della quota', pg.is_visible('#ts-fr'))
        pg.fill('#ts-testo', '420 ±0,5'); pg.press('#ts-testo', 'Tab'); time.sleep(1.5)
        chk('testo della quota nel foglio', '420 ±0,5' in pg.inner_html('#te-foglio'))
        # testi più grandi
        pg.locator('summary', has_text='Altezza dei testi').click()
        pg.fill('[data-t="quote"]', '4'); pg.press('[data-t="quote"]', 'Tab'); time.sleep(1.5)
        chk('altezza quote salvata', api('drawing_preview', None)['sheets'][0]['ritocchi'].get('testi', {}).get('quote') == 4)
        pg.fill('[data-t="frecce"]', '5'); pg.press('[data-t="frecce"]', 'Tab'); time.sleep(1.5)
        chk('frecce della tavola salvate', api('drawing_preview', None)['sheets'][0]['ritocchi'].get('testi', {}).get('frecce') == 5)
        # quota nuova: due punti della stessa vista
        pg.click('[data-str="quota"]')
        o = next(o for o in api('drawing_preview', None)['sheets'][0]['oggetti'] if o['id'] == v)
        pts = sorted(o['punti'], key=lambda p: (p[1], p[0]))
        A, B = pts[0], max((p for p in pts if abs(p[1] - pts[0][1]) < 0.01), key=lambda p: p[0])
        def schermo(pp):
            return pg.evaluate("""([x, y]) => { const s = document.querySelector('#te-foglio svg'), H = s.viewBox.baseVal.height;
                const pt = s.createSVGPoint(); pt.x = x; pt.y = H - y; const q = pt.matrixTransform(s.getScreenCTM()); return [q.x, q.y]; }""", pp)
        for pp in (A, B):
            sx, sy = schermo(pp); pg.mouse.move(sx, sy); time.sleep(0.1); pg.mouse.down(); pg.mouse.up(); time.sleep(0.4)
        time.sleep(1.2)
        r = api('drawing_preview', None)['sheets'][0]['ritocchi']
        chk('quota aggiunta ' + str(r.get('aggiunte')), len(r.get('aggiunte') or []) == 1)
        chk('dice 420 tondo e sta fuori dalla vista', '420,01' not in pg.inner_html('#te-foglio') and r['aggiunte'][0]['d'] < 0)
        # una nota
        pg.click('[data-str="nota"]')
        fb = pg.locator('#te-foglio svg').bounding_box()
        pg.mouse.click(fb['x'] + fb['width'] * 0.1, fb['y'] + fb['height'] * 0.8); time.sleep(0.5)
        pg.fill('#nt-t', 'Sbavare tutti i bordi'); pg.click('#m-ok'); time.sleep(1.5)
        chk('nota sul foglio', 'Sbavare tutti i bordi' in pg.inner_html('#te-foglio'))
        # cartiglio: cliente
        pg.click('[data-str="sel"]')
        pg.locator('summary', has_text='Cartiglio').click()
        pg.fill('[data-c="cliente"]', 'Officine Rossi'); pg.press('[data-c="cliente"]', 'Tab')
        time.sleep(2)
        chk('cliente nel cartiglio', 'Officine Rossi' in pg.inner_html('#te-foglio'))
        pg.screenshot(path=str(OUT / '2_ritoccata.png'))
        # diametro con un clic sul cerchio, angolo con tre clic, saldatura (punta + simbolo + finestra)
        def schermo_f(pp):
            return pg.evaluate("""([x, y]) => { const s = document.querySelector('#te-foglio svg'), H = s.viewBox.baseVal.height + s.viewBox.baseVal.y;
                const pt = s.createSVGPoint(); pt.x = x; pt.y = %s - y; const q = pt.matrixTransform(s.getScreenCTM()); return [q.x, q.y]; }""" % 'window.__altezzaFoglio', pp)
        pg.evaluate("window.__altezzaFoglio = 0")
        alt = pg.evaluate("window.__tavole.foglio()")                  # il foglio com'è nell'editor (col cartiglio di adesso)
        pg.evaluate(f"window.__altezzaFoglio = {alt['size'][1]}")
        def clic_f(pp):
            sx, sy = schermo_f(pp); pg.mouse.move(sx, sy); time.sleep(0.15); pg.mouse.down(); pg.mouse.up(); time.sleep(0.35)
        va = next(o for o in alt['oggetti'] if o['id'] == 'vista:alto')
        chk(f"cerchi riconosciuti nella vista: {len(va['cerchi'])}", len(va['cerchi']) >= 1)
        c0 = va['cerchi'][0]
        pg.click('[data-str="diametro"]'); clic_f([c0['c'][0] + c0['r'] * 0.707, c0['c'][1] + c0['r'] * 0.707]); time.sleep(1.2)
        chk('diametro sul foglio', 'Ø40' in pg.inner_html('#te-foglio'))
        pts = sorted(va['punti'], key=lambda q: (q[1], q[0]))
        A = max((q for q in pts if abs(q[1] - pts[0][1]) < 0.01), key=lambda q: q[0]); V = pts[0]
        B = max((q for q in pts if abs(q[0] - V[0]) < 0.01), key=lambda q: q[1])
        pg.click('[data-str="angolo"]')
        clic_f(A); clic_f(V); clic_f(B); time.sleep(1.2)
        chk('angolo di 90° sul foglio', '90°' in pg.inner_html('#te-foglio'))
        pg.click('[data-str="saldatura"]'); clic_f(V); clic_f([V[0] + 20, V[1] + 15]); time.sleep(0.5)
        pg.fill('#sd-a', '4'); pg.check('#sd-giro'); pg.click('#m-ok'); time.sleep(1.5)
        chk('saldatura a4 sul foglio', '>a4<' in pg.inner_html('#te-foglio'))
        r = api('drawing_preview', None)['sheets'][0]['ritocchi']
        chk('salvati: diametro, angolo, saldatura', len(r.get('diametri', [])) == 1 and len(r.get('angoli', [])) == 1 and len(r.get('saldature', [])) == 1)
        # zoom con la rotella e Adatta
        prima = pg.get_attribute('#te-foglio svg', 'viewBox')
        fb = pg.locator('#te-foglio svg').bounding_box(); pg.mouse.move(fb['x'] + fb['width'] / 3, fb['y'] + fb['height'] / 2)
        for _ in range(4): pg.mouse.wheel(0, -200); time.sleep(0.1)
        dopo = pg.get_attribute('#te-foglio svg', 'viewBox')
        chk(f'zoom: {prima} → {dopo}', prima != dopo and float(dopo.split()[2]) < float(prima.split()[2]))
        pg.screenshot(path=str(OUT / '2b_zoom.png'))
        pg.click('#te-adatta'); time.sleep(0.3)
        chk('Adatta torna al foglio intero', [float(x) for x in pg.get_attribute('#te-foglio svg', 'viewBox').split()] == [float(x) for x in prima.split()])
        pg.click('[data-str="sel"]')
        pg.screenshot(path=str(OUT / '2c_simboli.png'))
        # Annulla toglie l'ultimo ritocco
        pg.click('#te-undo'); time.sleep(1.5)
        chk('Annulla toglie la saldatura', '>a4<' not in pg.inner_html('#te-foglio'))
        pg.click('#te-auto'); time.sleep(1.5)
        chk('Rimetti automatico', not api('drawing_preview', None)['sheets'][0]['ritocchi'])
        pg.screenshot(path=str(OUT / '3_automatica.png'))
        pg.click('#te-chiudi'); time.sleep(0.3)
        chk('editor chiuso', not pg.is_visible('#tav-ed'))
        chk('nessun errore ' + str(err), not err)
        b.close()
finally:
    srv.kill()
print(f'{sum(ok)}/{len(ok)}')
