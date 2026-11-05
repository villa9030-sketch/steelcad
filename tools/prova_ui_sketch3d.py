r"""Scheletro in 3D (05/11, idea dallo «sketch 3D» di SolidCraft): telai che non stanno su un piano solo.

1. tronco di piramide (telaio di tramoggia): base con le frecce, chiusa con «Fino a un punto» (si aggancia), gambe
   «Inclinato» con l'anteprima mentre scrivi, il telaio sopra «Parallelo a un tubo», i tagli e la distinta;
2. parapetto di una scala: il cosciale «Fino a un punto», due montanti, il corrimano che si aggancia, poi «Misure
   della linea»: cambio l'angolo della scala e tutto segue; tema scuro.

    .venv\Scripts\python.exe tools\prova_ui_sketch3d.py cartella_foto [porta]
"""
import os, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
PY = Path(os.environ.get('RADIUS_PY') or sys.executable)
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
SP.mkdir(parents=True, exist_ok=True)
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 5331
CHROME = os.environ.get('RADIUS_CHROME') or 'C:/Users/Stefano/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
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
    time.sleep(0.5)
    pg.screenshot(path=str(SP / f'{n[0]:02d}.png'))


def ok(cosa, v):
    ok_tutti.append(bool(v))
    print(('OK  ' if v else 'NO  ') + cosa, flush=True)


try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        pg = b.new_page(viewport={'width': 1500, 'height': 900}); err = []
        pg.on('pageerror', lambda e: err.append(str(e))); pg.on('console', lambda m: m.type == 'error' and err.append(m.text + ' ' + str(m.location)))
        pg.goto(f'http://127.0.0.1:{PORTA}/?dev'); pg.wait_for_function('window.__steelcad && window.__steelcad.ready', timeout=60000)
        api = lambda nm, *a: pg.evaluate("async ([n, a]) => (await (await fetch('/api/' + n, {method: 'POST', body: JSON.stringify(a)})).json())", [nm, list(a)])
        time.sleep(1)

        def pronta():
            pg.wait_for_function('window.__steelcad.state.scene_version === window.__steelcad.sceneVersion')
            time.sleep(0.6)

        def pezzi():
            return pg.evaluate('window.__steelcad.state.cutlist.pieces')

        def aspetta_pezzi(k):
            pg.wait_for_function(f'window.__steelcad.state.cutlist && window.__steelcad.state.cutlist.pieces === {k}', timeout=30000)
            pronta()

        def nodo_in(xyz, tol=1):
            return pg.evaluate("""([p, t]) => (window.__steelcad.nodes.find(n => Math.hypot(n.xyz[0] - p[0], n.xyz[1] - p[1], n.xyz[2] - p[2]) < t) || {}).id""", [xyz, tol])

        def scegli_nodo(nid):
            pg.evaluate("id => window.__steelcad.select(id)", nid)
            pg.wait_for_selector('[data-n3d]'); time.sleep(0.6)

        def anteprima_pronta():
            pg.wait_for_function("(() => { const s = document.querySelector('#n-3d .ant-stato'); return s && !s.classList.contains('calcolo') && /ok|no/.test(s.className); })()", timeout=30000)
            time.sleep(0.4)

        def freccia(dir_, lung):
            pg.fill('#n-len', str(lung))
            prima = pezzi() or 0
            pg.click(f'[data-freccia="{dir_}"]')
            aspetta_pezzi(prima + 1)

        def iso():
            pg.evaluate("window.__steelcad.runCmd('view_iso')"); time.sleep(0.8)
            pg.evaluate("window.__steelcad.runCmd('fit')"); time.sleep(1.2)

        # ---------------------------------------------------------------- 1. tronco di piramide
        pg.evaluate("window.__steelcad.nuovo('vuoto')")
        pg.click('#n-ok')
        pg.wait_for_function("window.__steelcad.nodes.length === 1")
        scegli_nodo(pg.evaluate("window.__steelcad.nodes[0].id"))
        pg.fill('#n-prof', '40x40x3')
        freccia('destra', 600)
        freccia('dietro', 600)
        freccia('sinistra', 600)
        # chiudo la base: «Fino a un punto» 600 avanti → si aggancia al primo angolo
        pg.click('[data-n3d="punto"]'); time.sleep(0.3)
        pg.fill('#l3-y', '-600'); anteprima_pronta()
        foto('base: «Fino a un punto» 600 avanti, anteprima in azzurro')
        pg.click('#l3-ok'); aspetta_pezzi(4)
        ok('base chiusa: 4 tubi da 600 a 45°, nessun angolo in più', pezzi() == 4 and len(pg.evaluate('window.__steelcad.nodes')) == 4)
        # la gamba inclinata dal primo angolo: su, 14° verso sinistra e 14° verso avanti, alta 800
        scegli_nodo(nodo_in([0, 0, 0]))
        iso()
        pg.fill('#n-len', '800')
        pg.click('[data-n3d="inclinata"]'); time.sleep(0.3)
        pg.fill('#l3-g1', '14'); pg.select_option('#l3-d1', 'sinistra')
        pg.fill('#l3-g2', '14'); pg.select_option('#l3-d2', 'avanti')
        pg.select_option('#l3-mis', 'freccia'); anteprima_pronta()
        pg.evaluate("document.querySelector('#n-3d .ant-stato').scrollIntoView({block: 'center'})"); time.sleep(0.3)
        ok('anteprima della gamba inclinata', 'ok' in pg.get_attribute('#n-3d .ant-stato', 'class'))
        foto('gamba inclinata: su, 14° a sinistra e 14° avanti, alta 800 (anteprima)')
        pg.click('#l3-ok'); aspetta_pezzi(5)
        alto = pg.evaluate("Math.max(...window.__steelcad.nodes.map(n => n.xyz[2]))")
        ok(f'gamba alta 800 ({alto:.1f})', abs(alto - 800) < 0.5)
        # le altre tre gambe, con lo stesso pannello (le pieghe verso fuori)
        for xyz, d1, d2 in (([600, 0, 0], 'destra', 'avanti'), ([600, 600, 0], 'destra', 'dietro'), ([0, 600, 0], 'sinistra', 'dietro')):
            scegli_nodo(nodo_in(xyz))
            pg.fill('#n-len', '800')
            pg.click('[data-n3d="inclinata"]'); time.sleep(0.3)
            pg.fill('#l3-g1', '14'); pg.select_option('#l3-d1', d1)
            pg.fill('#l3-g2', '14'); pg.select_option('#l3-d2', d2)
            pg.select_option('#l3-mis', 'freccia')
            prima = pezzi(); pg.click('#l3-ok'); aspetta_pezzi(prima + 1)
        # il telaio sopra: dal capo della prima gamba, parallelo al tubo davanti della base (scelto cliccandolo nel 3D)
        import math
        sp = 800 * math.tan(math.radians(14))
        scegli_nodo(nodo_in([-sp, -sp, 800]))
        pg.fill('#n-len', str(round(600 + 2 * sp, 3)))
        pg.click('[data-n3d="parallela"]'); time.sleep(0.3)
        c = pg.evaluate("(() => { const b = new window.__steelcad.THREE.Box3().setFromObject(window.__steelcad.objs.get('ST1/M1').mesh); const c = b.getCenter(new window.__steelcad.THREE.Vector3()); return [c.x, c.y, c.z]; })()")
        xy = pg.evaluate("p => window.__steelcad.toScreen(p)", c)
        box = pg.locator('#c3d').bounding_box()
        pg.mouse.click(box['x'] + xy[0], box['y'] + xy[1]); time.sleep(0.6)
        scelto = pg.input_value('#l3-tubo')
        ok(f'tubo di riferimento scelto cliccandolo nel disegno ({scelto})', scelto == 'M1')
        anteprima_pronta()
        foto('telaio sopra: parallelo al tubo davanti (cliccato), anteprima')
        pg.click('#l3-ok'); aspetta_pezzi(9)
        # il resto del telaio sopra: si aggancia da solo agli angoli delle gambe
        for a_, b_ in (([600 + sp, -sp, 800], [600 + sp, 600 + sp, 800]), ([600 + sp, 600 + sp, 800], [-sp, 600 + sp, 800]),
                       ([-sp, 600 + sp, 800], [-sp, -sp, 800])):
            scegli_nodo(nodo_in(a_))
            pg.click('[data-n3d="punto"]'); time.sleep(0.3)
            d = [b_[i] - a_[i] for i in range(3)]
            pg.fill('#l3-x', str(round(d[0], 3))); pg.fill('#l3-y', str(round(d[1], 3))); pg.fill('#l3-z', '0')
            prima = pezzi(); pg.click('#l3-ok'); aspetta_pezzi(prima + 1)
        st = pg.evaluate('window.__steelcad.state')
        righe = [(r['profile'], r['length_mm'], r['qty'], r['cuts']) for r in st['cutlist']['rows']]
        print(righe)
        ok(f'tronco di piramide: 12 tubi, 8 angoli {righe}', pezzi() == 12 and len(pg.evaluate('window.__steelcad.nodes')) == 8)
        ok('gambe con i tagli storti in distinta', any(r[2] == 4 and any(c not in ('45°', '0°', 'dritto') for c in r[3]) and 700 < r[1] < 900 for r in righe))
        pg.evaluate("window.__steelcad.select('struct=ST1')"); time.sleep(1)
        iso()
        foto('tronco di piramide finito')
        pg.evaluate("window.__prova.showTab('cut', true)"); time.sleep(0.8)
        foto('distinta di taglio del tronco di piramide')
        pg.evaluate("window.__prova.applyTheme(true)"); time.sleep(0.8)
        foto('tronco di piramide, tema scuro')
        pg.evaluate("window.__prova.applyTheme(false)"); time.sleep(0.5)

        # ---------------------------------------------------------------- 2. parapetto di una scala
        pg.evaluate("window.__steelcad.nuovo('vuoto')")
        pg.click('#n-ok')
        pg.wait_for_function("window.__steelcad.nodes.length === 1 && !window.__steelcad.state.cutlist.pieces")
        A = pg.evaluate("window.__steelcad.nodes[0].id")
        scegli_nodo(A)
        pg.fill('#n-prof', '40x40x2')
        pg.click('[data-n3d="punto"]'); time.sleep(0.3)
        pg.fill('#l3-x', '2400'); pg.fill('#l3-z', '1500'); anteprima_pronta()
        pg.click('#l3-ok'); aspetta_pezzi(1)                              # il cosciale, inclinato come la scala
        scegli_nodo(A); freccia('su', 1000)                               # primo montante
        scegli_nodo(nodo_in([2400, 0, 1500])); freccia('su', 1000)        # ultimo montante
        scegli_nodo(nodo_in([0, 0, 1000]))
        pg.click('[data-n3d="punto"]'); time.sleep(0.3)
        pg.fill('#l3-x', '2400'); pg.fill('#l3-z', '1500'); anteprima_pronta()
        pg.click('#l3-ok'); aspetta_pezzi(4)                              # il corrimano: si aggancia al montante
        ok('parapetto: 4 tubi, 4 angoli (il corrimano agganciato)', len(pg.evaluate('window.__steelcad.nodes')) == 4)
        iso()
        # il cosciale cliccato: «Misure della linea» con lunghezza e angolo col montante
        cos = pg.evaluate("[...window.__steelcad.objs.keys()].find(k => /2\\.?830/.test(window.__steelcad.objs.get(k).data.name.replace(',', '.')))")
        pg.evaluate("id => window.__steelcad.select(id)", cos)
        pg.wait_for_selector('#p-linea .l3-misure', timeout=15000); time.sleep(0.5)
        ok('pannello del tubo: lunghezza della linea 2830,2', pg.input_value('#l3-len') == '2830,2')
        ang = pg.locator('[data-l3ang]').first
        ok(f'angolo col montante {ang.input_value()}', ang.input_value() in ('58', '58,0'))
        ang.fill('55'); pg.wait_for_function("(() => { const s = document.querySelector('#p-linea .ant-stato'); return s && /ok/.test(s.className); })()", timeout=30000)
        time.sleep(0.5)
        foto('scala: angolo col montante da 58° a 55°, anteprima (montante e corrimano seguono)')
        pg.locator('[data-l3ang-ok]').first.click(); time.sleep(0.5); pronta()
        z = pg.evaluate("Math.max(...window.__steelcad.nodes.map(n => n.xyz[2]))")
        ok(f'dopo l\'angolo il corrimano segue (alto {z:.0f})', abs(z - (1000 + 2830.19 * math.cos(math.radians(55)))) < 2)
        foto('parapetto dopo il cambio d’angolo')
        pg.evaluate("window.__prova.applyTheme(true)"); time.sleep(0.8)
        foto('parapetto, tema scuro, pannello misure della linea')
        pg.evaluate("window.__prova.applyTheme(false)")
        ok(f'nessun errore nella pagina {err[:3]}', not err)
        b.close()
finally:
    srv.kill()
print('TUTTO OK' if ok_tutti and all(ok_tutti) else 'QUALCOSA NON VA')
