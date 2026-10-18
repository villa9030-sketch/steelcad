"""Vetrina di SteelCAD: quadro elettrico da parete 600 × 800 × 200, IP55, costruito da zero.

    python tools/vetrina_quadro.py [cartella]          (di default Documenti/SteelCAD/vetrina_quadro)
    python tools/vetrina_quadro.py --live [cartella]   in diretta: si apre Chrome e si vede crescere ogni pezzo

Sei pezzi di lamiera (uno importato da un DXF di sviluppo), l'assieme montato, distinta, controllo interferenze,
tavole PDF con cartiglio e STEP dell'assieme. Raggi e K-factor sono valori di esempio (r = spessore, K 0,4):
per la produzione vanno quelli della tua piegatrice.
"""
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build123d as bd  # noqa: E402
import ezdxf  # noqa: E402
import numpy as np  # noqa: E402

from app.service import Service  # noqa: E402

LIVE = '--live' in sys.argv
_arg = [a for a in sys.argv[1:] if not a.startswith('--')]
D = Path(_arg[0]) if _arg else Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'vetrina_quadro'
D.mkdir(parents=True, exist_ok=True)
T0 = time.time()
s = None
DIRETTA = None                      # in diretta: manda gli eventi al browser e aspetta che li abbia mostrati
SKETCH = [None]                     # lo sketch aperto, da tenere a video
PAUSA = {'passo': 1.6, 'comando': 0.15}


def servizio():
    """In diretta si lavora sempre sullo stesso servizio, quello che il browser guarda."""
    return DIRETTA.svc if DIRETTA else Service()


def mostra(nuovo=False, key=None):
    if DIRETTA:
        DIRETTA.manda({'type': 'refresh', 'sketch': SKETCH[0], 'nuovo': nuovo, 'key': key})
        time.sleep(PAUSA['comando'])


def avvisa(testo):
    if DIRETTA:
        DIRETTA.manda({'type': 'toast', 'text': testo})
        time.sleep(PAUSA['passo'])


NUOVI = ('new_project', 'new_assembly', 'import_dxf_create')
CHIUDONO = ('create_from_sketch', 'sheet_fold', 'sheet_tab')


def ok(nome, *a):
    r = getattr(s, nome)(*a)
    if not r.get('ok'):
        raise SystemExit(f'\nERRORE {nome}{a}: {r.get("message")}')
    if DIRETTA and nome not in ('sketch_view', 'import_dxf', 'save', 'export_drawings', 'asm_export_step'):
        if nome in ('sketch_on_face', 'sketch_on_flat'):
            SKETCH[0] = r['sketch']
        elif nome in CHIUDONO:
            SKETCH[0] = None
        mostra(nuovo=nome in NUOVI)
    return r


def bordi(sid):
    """Ingombro della faccia nello sketch (i bordi di riferimento)."""
    v = s.sketch_view(sid)['sketch']
    xs, ys = [], []
    for ln in v['lines']:
        if ln['ref'] and not ln.get('xray'):
            xs += [ln['xa'][0], ln['xb'][0]]
            ys += [ln['xa'][1], ln['xb'][1]]
    return min(xs), min(ys), max(xs), max(ys)


def nuovi(sid, kind=None):
    v = s.sketch_view(sid)['sketch']
    out = []
    for k in ('lines', 'arcs', 'circles'):
        if kind and k != kind:
            continue
        out += [e['id'] for e in v.get(k, []) if not e['ref'] and not e.get('xray')]
    return out


def raccorda(sid, a, b, r):
    """Raccorda i quattro angoli del rettangolo a–b disegnato nello sketch."""
    v = s.sketch_view(sid)['sketch']
    xs, ys = (a[0], b[0]), (a[1], b[1])
    for p in v['points']:
        if p['id'] != 'O' and any(abs(p['xy'][0] - x) < 1e-6 for x in xs) and any(abs(p['xy'][1] - y) < 1e-6 for y in ys):
            ok('sketch_fillet', sid, p['id'], r)


def titolo(t):
    print(f'\n[{time.time() - T0:5.1f}s] {t}', flush=True)
    avvisa(t)


def passo(t):
    print(f'   · {t}', flush=True)
    avvisa(t[0].upper() + t[1:])


def salva(nome):
    st = s.state()
    if st['errors']:
        raise SystemExit(f'{nome}: ' + '; '.join(e['message'] for e in st['errors']))
    p = D / f'{nome}.steelcad'
    ok('save', str(p))
    b = s.result.body
    sz = [round(x, 1) for x in bd.Shape.cast(b.shape).bounding_box().size]
    print(f'   = {nome}: {len(s.doc.features)} feature, ingombro {sz}, sviluppo {[round(x, 1) for x in b.sheet.flat_size]}', flush=True)
    return p


def lamiera(nome, L, P, sp, materiale='S235'):
    global s
    s = servizio()
    ok('new_project', 'lamiera', {'name': nome, 'larghezza': L, 'profondita': P, 'spessore': sp, 'raggio': sp, 'k': 0.4})
    if materiale != 'S235':
        s.doc.material = materiale
        s._rebuild()
        mostra()


# Cerniere a bandiera: due ali di lamiera per cerniera (lato cassa, lato porta), perno vite M5 + dado autobloccante.
# Coordinate della cassa prima di metterla in piedi: x larghezza (0..600), y altezza (0..800), z profondità
# (schiena a 0, cornice a 200). Asse delle cerniere verticale in x = -14, z = 180: dietro la punta dei bordi della
# porta (183,5), così aprendo i bordi si allontanano dalla cassa invece di entrarci.
CERNIERE = (150, 640)        # y della faccia sotto dell'ala lato cassa (cerniera bassa, alta)
ASSE = (-14.0, 180.0)        # x, z dell'asse dei perni
LUCE = 1.0                   # tra le due ali (rondella)


# ============================================================================== 1. cassa
def cassa():
    titolo('1. CASSA 600 × 800 × 200, sp. 1,5')
    lamiera('Cassa', 600, 800, 1.5)
    passo('quattro pareti da 200, angoli chiusi con sormonto (fessura 0,5)')
    for e in ('L1', 'L2', 'L3', 'L4'):
        ok('add_flange', 'SM1', e, {'length': '200'})
    for a, b in (('FL1', 'FL2'), ('FL1', 'FL4'), ('FL3', 'FL2'), ('FL3', 'FL4')):
        ok('set_corner', 'SM1', a, b, 'over', 0.5)
    passo('cornice battuta porta: bordi da 25 verso l’interno, angoli tagliati a 45°')
    for p in ('FL1', 'FL2', 'FL3', 'FL4'):
        ok('add_flange', 'SM1', None, {'length': '25', 'angle': 90, 'direction': 'up'}, p)
    ok('set_tip_corners', 'SM1', 'miter')
    passo('la cornice è un’unica faccia (quattro bordi uniti a 45°): 8 asole 5 × 12 per i fermagli della guarnizione;'
          ' è anche la battuta della camma della serratura')
    sid = ok('sketch_on_face', 'SM1/FL5/esterno')['sketch']
    x0, y0, x1, y1 = bordi(sid)
    for y in (y0 + 11, y1 - 11):
        for x in (x0 + 150, x1 - 150):
            ok('sketch_add_slot', sid, [x - 3.5, y], [x + 3.5, y], 2.5)
    for x in (x0 + 11, x1 - 11):
        for y in (y0 + 250, y1 - 250):
            ok('sketch_add_slot', sid, [x, y - 3.5], [x, y + 3.5], 2.5)
    ok('create_from_sketch', sid, 'cut', {})

    passo('fondo: 3 passacavi M32, 4 M25, 4 M20')
    sid = ok('sketch_on_face', 'SM1/FL1/esterno')['sketch']
    x0, y0, x1, y1 = bordi(sid)
    for i in range(3):
        ok('sketch_add_circle', sid, [x0 + 330 + i * 70, y0 + 100], 16.25)
    for i in range(4):
        ok('sketch_add_circle', sid, [x0 + 320 + i * 55, y0 + 45], 12.75)
        ok('sketch_add_circle', sid, [x0 + 320 + i * 55, y0 + 155], 10.25)
    ok('create_from_sketch', sid, 'cut', {})

    passo('fondo: finestra per piastra passacavi 200 × 70 raccordata R8, con 4 fori filettati M5')
    sid = ok('sketch_on_face', 'SM1/FL1/esterno')['sketch']
    ok('sketch_add_rectangle', sid, [x0 + 60, y0 + 65], [x0 + 260, y0 + 135])
    raccorda(sid, [x0 + 60, y0 + 65], [x0 + 260, y0 + 135], 8)
    ok('create_from_sketch', sid, 'cut', {})
    sid = ok('sketch_on_face', 'SM1/FL1/esterno')['sketch']
    for x, y in ((45, 50), (275, 50), (45, 150), (275, 150)):
        ok('sketch_add_circle', sid, [x0 + x, y0 + y], 2.1)
    ok('sketch_hole_type', sid, nuovi(sid, 'circles'), {'tipo': 'filettato', 'M': 'M5'})
    ok('create_from_sketch', sid, 'cut', {})

    passo('fianchi: 2 × 6 persiane di aerazione 90 × 8, alte 4')
    for f in ('SM1/FL2/esterno', 'SM1/FL4/esterno'):
        sid = ok('sketch_on_face', f)['sketch']
        x0, y0, x1, y1 = bordi(sid)
        for xa in (x0 + 140, x1 - 230):
            for k in range(6):
                y = y0 + 45 + k * 18
                ok('sketch_add_polyline', sid, [[xa, y], [xa + 90, y]], False)
        ok('create_from_sketch', sid, 'louver', {'width': 8, 'height': 4})

    passo('fianco sinistro: 2 + 2 fori Ø5,2 per rivettare le ali delle cerniere')
    sid = ok('sketch_on_face', 'SM1/FL4/esterno')['sketch']
    for yb in CERNIERE:                       # sul fianco sinistro: y = 798 − u, z = v + 3
        for z in (158, 170):
            ok('sketch_add_circle', sid, [798 - (yb + 17.6), z - 3], 2.6)
    ok('create_from_sketch', sid, 'cut', {})

    passo('schiena: 4 fori filettati M6 per la piastra di montaggio, 4 fori Ø8,5 per le staffe a muro')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for x, y in ((80, 80), (520, 80), (80, 720), (520, 720)):
        ok('sketch_add_circle', sid, [x, y], 2.5)
    ok('sketch_hole_type', sid, nuovi(sid, 'circles'), {'tipo': 'filettato', 'M': 'M6'})
    ok('create_from_sketch', sid, 'cut', {})
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for x, y in ((150, 30), (450, 30), (150, 700), (450, 700)):
        ok('sketch_add_circle', sid, [x, y], 4.25)
    ok('create_from_sketch', sid, 'cut', {})
    passo('schiena: 4 imbutiture di irrigidimento Ø40, profonde 3')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for x, y in ((300, 200), (300, 400), (300, 600), (180, 400)):
        ok('sketch_add_circle', sid, [x, y], 20)
    ok('create_from_sketch', sid, 'dimple', {'depth': 3})

    passo('sullo sviluppo: asola passacavi 16 × 70 che attraversa la piega schiena/fondo')
    sid = ok('sketch_on_flat', 'SM1')['sketch']
    ok('sketch_add_slot', sid, [100, -40], [100, 25], 8)
    ok('create_from_sketch', sid, 'cut', {})

    return salva('cassa')


# ============================================================================== 2. porta
def porta():
    titolo('2. PORTA 605 × 805, sp. 1,5: abbraccia la cassa, cerniere a bandiera a sinistra')
    lamiera('Porta', 605, 805, 1.5)
    passo('bordi da 22 che abbracciano le pareti con 1 mm di gioco; 4 mm di luce sulla cornice per la guarnizione')
    for e in ('L1', 'L2', 'L3', 'L4'):
        ok('add_flange', 'SM1', e, {'length': '22'})
    for a, b in (('FL1', 'FL2'), ('FL1', 'FL4'), ('FL3', 'FL2'), ('FL3', 'FL4')):
        ok('set_corner', 'SM1', a, b, 'over', 0.5)
    passo('orlo a 180° verso fuori sul bordo della serratura (dentro c’è solo 1 mm di gioco); il bordo cerniere resta dritto')
    ok('add_flange', 'SM1', None, {'length': '10', 'angle': 180, 'direction': 'down'}, 'FL4')
    passo('bordo cerniere: 2 + 2 fori Ø5,2 per le ali della porta')
    sid = ok('sketch_on_face', 'SM1/FL2/esterno')['sketch']
    for yb in CERNIERE:                       # sul bordo della porta: y = u − 0,5, z = 202,5 − v (cassa)
        yd = yb + 2 + LUCE
        for z in (190, 199):
            ok('sketch_add_circle', sid, [yd + 17.6 + 0.5, 202.5 - z], 2.6)
    ok('create_from_sketch', sid, 'cut', {})
    passo('finestra d’ispezione 420 × 220 con angoli R15; 8 fori Ø4,5 per il vetro')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    ok('sketch_add_rectangle', sid, [92.5, 482.5], [512.5, 702.5])
    raccorda(sid, [92.5, 482.5], [512.5, 702.5], 15)
    ok('create_from_sketch', sid, 'cut', {})
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for x in (77.5, 302.5, 527.5):
        for y in (467.5, 717.5):
            ok('sketch_add_circle', sid, [x, y], 2.25)
    for x in (77.5, 527.5):
        ok('sketch_add_circle', sid, [x, 592.5], 2.25)
    ok('create_from_sketch', sid, 'cut', {})
    passo('serratura a quarto di giro dal lato opposto alle cerniere: foro Ø22 con chiavetta, la camma va dietro la cornice')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    cx, cy = 47.5, 402.5
    a0 = math.degrees(math.asin(2 / 11))
    pts = [[cx + 11 * math.cos(math.radians(90 + a0 + k * (360 - 2 * a0) / 24)),
            cy + 11 * math.sin(math.radians(90 + a0 + k * (360 - 2 * a0) / 24))] for k in range(25)]
    ok('sketch_add_polyline', sid, pts + [[cx + 2, cy + 13.5], [cx - 2, cy + 13.5]], True)
    ok('create_from_sketch', sid, 'cut', {})
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    ok('sketch_add_polygon', sid, [cx, cy - 70], [cx + 14, cy - 70], 6)
    ok('create_from_sketch', sid, 'cut', {})
    passo('griglia di aerazione in basso: 5 × 3 persiane 60 × 6')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for i in range(5):
        for k in range(3):
            x, y = 72.5 + i * 95, 72.5 + k * 22
            ok('sketch_add_polyline', sid, [[x, y], [x + 60, y]], False)
    ok('create_from_sketch', sid, 'louver', {'width': 6, 'height': 3})
    return salva('porta')


# ============================================================================== 2b. cerniere
def ala(nome, titolo_ala, contorno, perno, fori, verso):
    """Un'ala della cerniera a bandiera: contorno disegnato → lamiera, flangia di fissaggio sul primo lato,
    foro del perno sull'ala, fori di fissaggio sulla flangia (disegnati sullo sviluppo)."""
    global s
    s = servizio()
    ok('new_project', 'zero', {'name': titolo_ala})
    passo('contorno a bandiera disegnato nello sketch, poi “diventa lamiera” sp. 2')
    ok('sketch_add_polyline', 'S1', contorno, True)
    ok('create_from_sketch', 'S1', 'sheet', {'thickness': 2, 'radius': 2, 'k': 0.4})
    sk = s.doc.sketch('S1')

    def xy(pid):
        return (round(sk.entities[pid]['x'], 3), round(sk.entities[pid]['y'], 3))
    lato = next(k for k, e in sk.entities.items() if e['kind'] == 'line'
                and {xy(e['a']), xy(e['b'])} == {tuple(map(float, contorno[0])), tuple(map(float, contorno[1]))})
    passo('flangia di fissaggio da 25 piegata sul lato d’attacco; foro Ø5,3 del perno; 2 fori Ø5,2 di fissaggio')
    ok('add_flange', 'SM1', lato, {'length': '25', 'direction': verso})
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    ok('sketch_add_circle', sid, perno, 2.65)
    ok('create_from_sketch', sid, 'cut', {})
    sid = ok('sketch_on_flat', 'SM1')['sketch']
    for c in fori:
        ok('sketch_add_circle', sid, c, 2.6)
    ok('create_from_sketch', sid, 'cut', {})
    return salva(nome)


def cerniere():
    titolo('2b. CERNIERA A BANDIERA: due ali di lamiera, perno M5')
    a = ala('ala_cassa', 'Ala cerniera lato cassa',
            [[0, 0], [28, 0], [34, 6], [37, 10], [37, 18], [33, 21], [0, 21]], [30, 14], [[8, -14], [20, -14]], 'down')
    b = ala('ala_porta', 'Ala cerniera lato porta',
            [[0, 0], [17, 0], [27, 3], [30, 7.5], [30, 15.5], [26, 18.5], [0, 18.5]], [23, 11.5], [[4, -14], [13, -14]], 'up')
    return a, b


# ============================================================================== 3. piastra
def piastra():
    titolo('3. PIASTRA DI MONTAGGIO 500 × 700, sp. 2,5, zincata')
    lamiera('Piastra di montaggio', 500, 700, 2.5, 'DX51D')
    passo('bordi di irrigidimento da 20 sui lati lunghi')
    ok('add_flange', 'SM1', 'L2', {'length': '20', 'direction': 'down'})
    ok('add_flange', 'SM1', 'L4', {'length': '20', 'direction': 'down'})
    passo('4 asole di fissaggio 7 × 16 sugli M6 della schiena (gioco per regolarla)')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for x, y in ((30, 30), (470, 30), (30, 670), (470, 670)):
        ok('sketch_add_slot', sid, [x, y - 4.5], [x, y + 4.5], 3.5)
    ok('create_from_sketch', sid, 'cut', {})
    passo('foratura modulare: 11 × 2 fori filettati M5 per guide DIN (una asola + Serie)')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    ok('sketch_add_circle', sid, [50, 230], 2.1)
    ok('sketch_pattern', sid, nuovi(sid, 'circles'), 9, 50, 2, 250)
    ok('sketch_hole_type', sid, nuovi(sid, 'circles'), {'tipo': 'filettato', 'M': 'M5'})
    ok('create_from_sketch', sid, 'cut', {})
    passo('passaggio cavi: 2 finestre 300 × 40 con angoli R20')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    for y in (95, 600):
        ok('sketch_add_rectangle', sid, [100, y], [400, y + 40])
        raccorda(sid, [100, y], [400, y + 40], 15)
    ok('create_from_sketch', sid, 'cut', {})
    return salva('piastra')


# ============================================================================== 4. guida DIN (dal DXF)
def guida_din():
    titolo('4. GUIDA DIN 35 × 7,5 — importata da un DXF di sviluppo')
    dxf = D / 'guida_din_sviluppo.dxf'
    passo(f'scrivo lo sviluppo come lo manderebbe un fornitore: {dxf.name} (layer TAGLIO e PIEGA, asole 15 × 5,2 passo 25)')
    d = ezdxf.new()
    d.header['$INSUNITS'] = 4
    for ly in ('TAGLIO', 'PIEGA', 'TESTO'):
        d.layers.add(ly)
    m = d.modelspace()
    L, W = 450, 46.5
    m.add_lwpolyline([(0, 0), (L, 0), (L, W), (0, W)], close=True, dxfattribs={'layer': 'TAGLIO'})
    for x in range(25, L - 10, 25):
        m.add_lwpolyline([(x - 5, W / 2 - 2.6), (x + 5, W / 2 - 2.6)], dxfattribs={'layer': 'TAGLIO'})
        m.add_arc((x + 5, W / 2), 2.6, -90, 90, dxfattribs={'layer': 'TAGLIO'})
        m.add_lwpolyline([(x + 5, W / 2 + 2.6), (x - 5, W / 2 + 2.6)], dxfattribs={'layer': 'TAGLIO'})
        m.add_arc((x - 5, W / 2), 2.6, 90, 270, dxfattribs={'layer': 'TAGLIO'})
    for y in (4.75, 11.25, 35.25, 41.75):
        m.add_line((0, y), (L, y), dxfattribs={'layer': 'PIEGA'})
    m.add_text('GUIDA DIN TS35 sp 1 DX51D', dxfattribs={'layer': 'TESTO', 'height': 5}).set_placement((0, -10))
    d.saveas(dxf)
    global s
    s = servizio()
    r = ok('import_dxf', str(dxf))
    g = r['giro']
    passo(f'letto: contorno {g["size"][0]:.0f} × {g["size"][1]:.1f}, {g["tagli"]} asole, {len(g["pieghe"])} linee di piega; '
          f'dal testo: sp. {r["spessore"]}, {r["materiale"]}')
    ok('import_dxf_create', r['scelto'], {'name': 'Guida DIN TS35', 'material': r['materiale'], 'thickness': r['spessore'],
                                         'radius': 1, 'k': 0.4, 'angle': 90, 'direction': 'up',
                                         'bends': [{'direction': 'down'}, {}, {}, {'direction': 'down'}]})
    st = s.state()
    passo('sviluppo SteelCAD = disegno del fornitore: ' + ('sì' if not st['warnings'] else '; '.join(st['warnings'])))
    return salva('guida_din')


# ============================================================================== 5. staffa a muro
def staffa():
    titolo('5. STAFFA A MURO, sp. 3, piegata su linea')
    lamiera('Staffa a muro', 160, 60, 3)
    passo('piega su linea sullo sviluppo a 70 mm: diventa una L')
    sid = ok('sketch_on_flat', 'SM1')['sketch']
    ok('sketch_add_polyline', sid, [[70, -5], [70, 65]], False)
    ok('sheet_fold', sid, 90, 'up', False)
    passo('foro Ø8,5 verso la cassa, asola 9 × 25 per il tassello a muro, nervatura (imbutitura)')
    sid = ok('sketch_on_face', 'SM1/sopra')['sketch']
    ok('sketch_add_circle', sid, [30, 30], 4.25)
    ok('create_from_sketch', sid, 'cut', {})
    names = [n for n in s.result.body.names if n.endswith('/esterno') and n.count('/') == 2]
    sid = ok('sketch_on_face', names[0])['sketch']
    x0, y0, x1, y1 = bordi(sid)
    cx = (x0 + x1) / 2
    ok('sketch_add_slot', sid, [cx, y1 - 45], [cx, y1 - 20], 4.5)
    ok('create_from_sketch', sid, 'cut', {})
    passo('spigoli della L raccordati R12')
    sid = ok('sketch_on_face', names[0])['sketch']
    v = s.sketch_view(sid)['sketch']
    alti = sorted(v['points'], key=lambda p: -p['xy'][1])
    fatti = 0
    for p in alti:
        if p['id'] != 'O' and fatti < 2 and abs(p['xy'][1] - y1) < 1e-6:
            ok('sketch_fillet', sid, p['id'], 12)
            fatti += 1
    return salva('staffa')


# ============================================================================== 6. tettuccio
def tettuccio():
    titolo('6. TETTUCCIO PARAPIOGGIA 640 × 231,5, sp. 1,5, inox')
    lamiera('Tettuccio', 640, 231.5, 1.5, 'AISI304')
    passo('gocciolatoio davanti 15 con orlo, fianchi 15, angoli chiusi: corti, la porta ci passa sotto quando si apre')
    ok('add_flange', 'SM1', 'L1', {'length': '15', 'direction': 'down'})
    ok('add_flange', 'SM1', 'L2', {'length': '15', 'direction': 'down'})
    ok('add_flange', 'SM1', 'L4', {'length': '15', 'direction': 'down'})
    for b in ('FL2', 'FL3'):
        ok('set_corner', 'SM1', 'FL1', b, 'over', 0.5)
    ok('add_flange', 'SM1', None, {'length': '8', 'angle': 180, 'direction': 'down'}, 'FL1')
    passo('dietro: bordo da 50 che scende sulla schiena (tettuccio rialzato di 20: aerazione), con 2 asole per fissarlo')
    ok('add_flange', 'SM1', 'L3', {'length': '50', 'direction': 'down'})
    sid = ok('sketch_on_face', 'SM1/FL5/esterno')['sketch']
    x0, y0, x1, y1 = bordi(sid)
    for x in (x0 + 170, x1 - 170):
        ok('sketch_add_slot', sid, [x - 5.5, (y0 + y1) / 2 + 2], [x + 5.5, (y0 + y1) / 2 + 2], 4.5)
    ok('create_from_sketch', sid, 'cut', {})
    return salva('tettuccio')


# ============================================================================== assieme
def assieme(F):
    global s
    titolo('7. ASSIEME: tutto al suo posto')
    s = servizio()
    ok('new_assembly', 'Quadro elettrico 600x800x200')
    ordine = [('cassa', 'Cassa'), ('piastra', 'Piastra di montaggio'), ('guida_din', 'Guida DIN alta'),
              ('guida_din', 'Guida DIN bassa'), ('porta', 'Porta'), ('staffa', 'Staffa basso sx'), ('staffa', 'Staffa basso dx'),
              ('staffa', 'Staffa alto sx'), ('staffa', 'Staffa alto dx'), ('tettuccio', 'Tettuccio'),
              ('ala_cassa', 'Cerniera bassa, ala cassa'), ('ala_cassa', 'Cerniera alta, ala cassa'),
              ('ala_porta', 'Cerniera bassa, ala porta'), ('ala_porta', 'Cerniera alta, ala porta')]
    for k, _ in ordine:
        ok('asm_insert', str(F[k]))
    ids = [i['id'] for i in s.asm.instances]
    for iid, (_, nome) in zip(ids, ordine):
        ok('asm_set', iid, {'name': nome})
    ok('asm_set', ids[0], {'fixed': True})

    def bbox(iid):
        b = bd.Shape.cast(s.asm_parts[s.asm.instance(iid)['file']].shape).bounding_box()
        return np.array([b.min.X, b.min.Y, b.min.Z]), np.array([b.max.X, b.max.Y, b.max.Z])

    def posa(iid, R, punto_locale, punto_mondo):
        """Ruota con R e porta punto_locale (coordinate del pezzo) in punto_mondo."""
        R = np.array(R, dtype=float)
        T = np.array(punto_mondo, dtype=float) - R @ np.array(punto_locale, dtype=float)

        def fn():
            i = s.asm.instance(iid)
            i['R'], i['T'] = R.tolist(), T.tolist()
        r = s._asm_change(f'Posa {iid}', fn)
        if not r.get('ok'):
            raise SystemExit(r.get('message'))
        mostra()

    def angolo(iid, R, quale):
        """Il vertice del box d'ingombro ruotato: quale = (0|1, 0|1, 0|1) per min/max su X, Y, Z del mondo."""
        lo, hi = bbox(iid)
        R = np.array(R, dtype=float)
        best = None
        for cx in (lo[0], hi[0]):
            for cy in (lo[1], hi[1]):
                for cz in (lo[2], hi[2]):
                    w = R @ np.array([cx, cy, cz])
                    key = tuple(w[k] if quale[k] else -w[k] for k in range(3))
                    if best is None or key > best[0]:
                        best = (key, np.array([cx, cy, cz]))
        return best[1]

    I3 = np.eye(3)
    cassa_lo, cassa_hi = bbox(ids[0])
    passo(f'cassa ferma (schiena a z = {cassa_lo[2]:.1f}, apertura a z = {cassa_hi[2]:.1f})')
    zs = cassa_lo[2] + 1.5                                            # faccia interna della schiena
    passo('piastra centrata sulla schiena, sui bordi da 20: le asole cadono sugli M6')
    lo, hi = bbox(ids[1])
    posa(ids[1], I3, [lo[0], lo[1], lo[2]], [50, 50, zs])
    zp = zs + (hi[2] - lo[2])                                         # faccia davanti della piastra
    passo('guide DIN sulla piastra, centrate sulle file di M5 (y = 280 e 530)')
    for iid, y in ((ids[2], 280), (ids[3], 530)):
        lo, hi = bbox(iid)
        posa(iid, I3, [lo[0], (lo[1] + hi[1]) / 2, lo[2]], [75, y, zp])
    passo('cerniere: ali lato cassa sul fianco sinistro, ali lato porta sopra (1 mm di rondella), perni coassiali')
    Rc = np.array([[0.0, -1, 0], [0, 0, -1], [1, 0, 0]])           # ala cassa: X → z, Y → −x, Z → −y
    Ra = np.array([[0.0, -1, 0], [0, 0, 1], [-1, 0, 0]])           # ala porta: X → −z, Y → −x, Z → y
    for k, yb in enumerate(CERNIERE):
        posa(ids[10 + k], Rc, [0, 0, 0], [0, yb + 2, 150])
        posa(ids[12 + k], Ra, [0, 0, 0], [-2.5, yb + 2 + LUCE, 203])
    passo('porta: abbraccia la cassa, 4 mm davanti alla cornice')
    Rp = np.diag([-1.0, 1.0, -1.0])                                # girata attorno all’asse verticale
    posa(ids[4], Rp, [0, 0, 0], [602.5, -2.5, cassa_hi[2] + 5.5])
    accoppia(ids)
    passo('staffe a muro dietro la schiena, sui fori Ø8,5, gambe verso l’esterno')
    for iid, (x, y), R in ((ids[5], (150, 30), np.diag([-1.0, 1, -1])), (ids[6], (450, 30), np.diag([1.0, -1, -1])),
                           (ids[7], (150, 700), np.diag([-1.0, 1, -1])), (ids[8], (450, 700), np.diag([1.0, -1, -1]))):
        lo, hi = bbox(iid)
        zb = (R @ np.array([0, 0, hi[2]]))[2] > (R @ np.array([0, 0, lo[2]]))[2]
        z_top = hi[2] if zb else lo[2]                               # la faccia che va contro la schiena
        posa(iid, R, [30, 30, z_top], [x, y, cassa_lo[2]])
    passo('tettuccio 20 mm sopra la cassa: gocciolatoio davanti alla porta, bordo dietro a filo della schiena')
    Rt = np.array([[1.0, 0, 0], [0, 0, 1], [0, -1, 0]])
    lo, hi = bbox(ids[9])
    piano = (lo[2] + hi[2]) / 2
    # il punto più in basso della faccia sotto del tetto (z locale della base) va su y = 800
    posa(ids[9], Rt, [lo[0], hi[1], 0], [-20, 820 + 1.5, cassa_lo[2] - 1.5])     # 20 mm sopra la cassa
    del piano
    passo('tutto in piedi: altezza lungo Z, la porta guarda verso chi osserva')
    Q = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])

    def fn():
        for i in s.asm.instances:
            i['R'] = (Q @ np.array(i['R'])).tolist()
            i['T'] = (Q @ np.array(i['T'])).tolist()
    s._asm_change('In piedi', fn)
    mostra(nuovo=True)
    return ids


def faccia(iid, nome=None, kind='piana', vicino=None, r=None):
    """L'indice della faccia del pezzo: per nome e tipo, la più vicina a un punto (coordinate del pezzo)."""
    best = None
    for o in s.scene()['objects']:
        if o['id'] != iid:
            continue
        for f in o['faces']:
            inf = s._asm_face(iid, f['index'])
            if inf['kind'] != kind or (nome and inf['name'] != nome) or (r and abs(inf.get('r', 0) - r) > 0.01):
                continue
            d = float(np.linalg.norm(np.array(inf['p']) - np.array(vicino))) if vicino is not None else 0
            if best is None or d < best[0]:
                best = (d, f['index'])
    if best is None:
        raise SystemExit(f'faccia non trovata: {iid} {nome} {kind} {vicino}')
    return best[1]


def accoppia(ids):
    """La catena vera: cassa → ala cassa (faccia + 2 fori) → ala porta (perno + ali) → porta (faccia + 2 fori)."""
    def mate(tipo, a, b, offset=0):
        r = s.asm_add_mate(tipo, {'inst': a[0], 'face': a[1]}, {'inst': b[0], 'face': b[1]}, offset, False)
        if not r.get('ok'):
            raise SystemExit(f'accoppiamento {tipo} {a} {b}: {r.get("message")}')
        mostra()
    cassa = ids[0]
    for k, yb in enumerate(CERNIERE):
        ac, ap = ids[10 + k], ids[12 + k]
        passo(f'cerniera {"bassa" if k == 0 else "alta"}: ala cassa faccia su faccia sul fianco e foro su foro sui rivetti')
        mate('faccia', (cassa, faccia(cassa, 'SM1/FL4/esterno')), (ac, faccia(ac, None, 'piana', [14, 0, -12])))
        for x in (8, 20):
            mate('asse', (cassa, faccia(cassa, None, 'cilindrica', [0, 799 - (799 - (yb + 17.6)), x + 150], 2.6)),
                 (ac, faccia(ac, None, 'cilindrica', [x, 1, -15.6], 2.6)))
        passo('ala porta: perno coassiale e ala sull’ala con 1 mm di rondella (resta libera di ruotare)')
        mate('asse', (ac, faccia(ac, None, 'cilindrica', [30, 14, 1], 2.65)), (ap, faccia(ap, None, 'cilindrica', [23, 11.5, 1], 2.65)))
        mate('faccia', (ac, faccia(ac, 'SM1/sotto')), (ap, faccia(ap, 'SM1/sotto')), LUCE)
    passo('porta sulle ali: faccia su faccia e foro su foro')
    porta = ids[4]
    for k, yb in enumerate(CERNIERE):
        ap = ids[12 + k]
        yd = yb + 2 + LUCE
        mate('faccia', (ap, faccia(ap, None, 'piana', [8, 0, 12])), (porta, faccia(porta, 'SM1/FL2/esterno')))
        for xa, z in ((4, 199), (13, 190)):
            mate('asse', (ap, faccia(ap, None, 'cilindrica', [xa, 1, 17.6], 2.6)),
                 (porta, faccia(porta, None, 'cilindrica', [605, yd + 17.6 + 2.5, 205.5 - z], 2.6)))
        if k == 0:
            break                                            # la seconda cerniera la tiene già la catena: basta una


def apri_porta(ids, gradi):
    """Ruota porta e ali lato porta attorno all'asse dei perni (dopo averla messa in piedi)."""
    Q = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])
    p = Q @ np.array([ASSE[0], 0, ASSE[1]])
    d = Q @ np.array([0.0, 1, 0])
    from cad_engine import assembly as A
    G = A._rot_axis(d, np.radians(-gradi))

    def fn():
        for iid in (ids[4], ids[12], ids[13]):
            i = s.asm.instance(iid)
            i['R'] = (G @ np.array(i['R'])).tolist()
            i['T'] = (G @ (np.array(i['T']) - p) + p).tolist()
    r = s._asm_change(f'Porta aperta {gradi}°', fn)
    if not r.get('ok'):
        raise SystemExit(r.get('message'))
    mostra()


def controlli(ids):
    titolo('8. CONTROLLI: interferenze, distinta, tavole, STEP')
    st = s.state()
    if st.get('warnings'):
        print('   avvisi:', st['warnings'])
    inter = s.asm_interferences().get('interferences', [])
    passo('interferenze a porta chiusa: ' + ('nessuna' if not inter else '; '.join(x['label'] for x in inter)))
    ok('save', str(D / 'quadro_elettrico.steelcad-asm'))
    passo('apro la porta sulle cerniere: 30°, 60°, 90°, 120°')
    fatto = 0
    for g in (30, 60, 90, 120):
        apri_porta(ids, g - fatto)
        fatto = g
        inter = s.asm_interferences().get('interferences', [])
        passo(f'porta aperta a {g}°: ' + ('nessuna interferenza' if not inter else 'tocca: ' + '; '.join(x['label'] for x in inter)))
    ok('save', str(D / 'quadro_porta_aperta.steelcad-asm'))
    apri_porta(ids, -fatto)
    from cad_engine import assembly as A
    righe = A.bom(s.asm, s.asm_parts)
    print('   DISTINTA')
    tot = 0
    for k, r in enumerate(righe, 1):
        print(f'   {k:2d}  {r["name"]:<24} {r["qty"]:>2} ×  {r["material"]:<8} sp. {r["thickness"] or "":<4} {r["mass_tot"]:7.2f} kg')
        tot += r['mass_tot']
    print(f'       {"totale":<24}{"":>32}{tot:7.2f} kg')
    ok('save', str(D / 'quadro_elettrico.steelcad-asm'))
    campi = {'azienda': 'Prova SteelCAD', 'disegnatore': 'SteelCAD', 'numero': 'QE-600-800', 'revisione': 'A',
             'note': 'Vetrina: raggi e K di esempio', 'formato': 'A3'}
    r = ok('export_drawings', str(D / 'quadro_elettrico_tavole.pdf'), campi, True)
    passo(r['message'])
    r = ok('asm_export_step', str(D / 'quadro_elettrico.step'))
    passo(r.get('message') or 'STEP salvato')


class Diretta:
    """Server dell'interfaccia nello stesso processo, sullo stesso servizio. Il browser (?dev&live) chiede gli eventi
    con live_next e conferma con live_ack: lo script va avanti solo quando il passo si è visto."""

    def __init__(self, porta=5150):
        import threading
        from app.dev_server import ApiProva, crea_server
        diretta = self

        class ApiLive(ApiProva):
            def live_next(self):
                return diretta._prossimi()

            def live_ack(self, n):
                with diretta.cv:
                    diretta.visti = max(diretta.visti, int(n))
                    diretta.cv.notify_all()
                return {'ok': True}

        self.api = ApiLive(D)
        self.svc = self.api._svc
        self.cv = threading.Condition()
        self.coda, self.n, self.visti, self.fine = [], 0, 0, False
        self.srv = crea_server(self.api, porta)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{porta}/?dev&live'

    def _prossimi(self):
        with self.cv:
            self.cv.wait_for(lambda: self.coda or self.fine, timeout=10)
            ev, self.coda = self.coda, []
            return {'ok': bool(ev) or self.fine, 'events': ev, 'n': self.n, 'end': self.fine and not ev}

    def manda(self, ev, aspetta=True):
        with self.cv:
            self.n += 1
            n = self.n
            self.coda.append(ev)
            self.cv.notify_all()
            if aspetta and not self.cv.wait_for(lambda: self.visti >= n, timeout=300):
                raise SystemExit('Il browser non risponde più: diretta interrotta.')

    def apri(self):
        """Chrome in una finestra a sé (se c'è), se no il browser predefinito; poi aspetta che la pagina sia pronta."""
        import glob
        import subprocess
        import webbrowser
        chrome = next(iter(glob.glob(r'C:\Program Files*\Google\Chrome\Application\chrome.exe')), None)
        if os.environ.get('VETRINA_SENZA_BROWSER'):
            pass
        elif chrome:
            subprocess.Popen([chrome, '--new-window', '--start-maximized', self.url])
        else:
            webbrowser.open(self.url)
        print(f'Diretta su {self.url} - aspetto il browser...', flush=True)
        self.manda({'type': 'toast', 'text': 'Diretta SteelCAD: quadro elettrico 600 × 800 × 200, costruito da zero'})
        time.sleep(2)


def main():
    global DIRETTA
    if LIVE:
        DIRETTA = Diretta()
        DIRETTA.apri()
    F = {'cassa': cassa(), 'porta': porta(), 'piastra': piastra(), 'guida_din': guida_din(), 'staffa': staffa(),
         'tettuccio': tettuccio()}
    F['ala_cassa'], F['ala_porta'] = cerniere()
    ids = assieme(F)
    controlli(ids)
    print(f'\nFatto in {time.time() - T0:.0f} s. File in {D}')
    if DIRETTA:
        mostra(key='0')
        DIRETTA.manda({'type': 'toast', 'text': f'Fatto: 8 pezzi, 14 copie, porta che apre a 120° senza interferenze, tavole PDF e STEP in {D}'})
        print('La pagina resta viva: chiudi questa finestra (Ctrl+C) quando hai finito di guardare.', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
