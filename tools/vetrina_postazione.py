"""Vetrina e prova di carico: una postazione di lavoro con cappa d'aspirazione che usa tutte le funzioni di SteelCAD.

    python tools/vetrina_postazione.py [cartella]          (di default Documenti/SteelCAD/vetrina_postazione)
    python tools/vetrina_postazione.py --live [cartella]   in diretta: si apre Chrome e si vede crescere ogni pezzo

Pezzi: banco (modello Telaio, misure cambiate dopo), piedini (Piastra), piano in lamiera con flange, angoli chiusi e
una serie di asole, staffe a L avvitate sotto il piano (foro su foro), vaschetta da contorno disegnato con smussi,
raccordi e imbutiture, carter con piega su linea, orlo, linguetta e persiane, cappa (raccordo quadro-tondo eccentrico)
con il cono calandrato sopra, portale da disegno che regge la cappa, scaffale, cancello di protezione, canalina
importata da DXF. Poi l'assieme, le interferenze, la distinta, le tavole, lo STEP, i DXF di taglio.

Un passo che non riesce non ferma la prova: si annota come "buco" (con il messaggio) e si va avanti. In fondo la lista.
"""
import importlib.util
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))
import build123d as bd  # noqa: E402

from app.service import Service  # noqa: E402
from cad_engine import assembly as A  # noqa: E402

LIVE = '--live' in sys.argv
_arg = [a for a in sys.argv[1:] if not a.startswith('--')]
D = Path(_arg[0]) if _arg else Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'vetrina_postazione'
# le vetrine non toccano la lista dei lavori recenti vera (una prova di carico la riempiva di file temporanei)
os.environ.setdefault('STEELCAD_HOME', __import__('tempfile').mkdtemp(prefix='steelcad_vetrina_'))
D.mkdir(parents=True, exist_ok=True)
T0 = time.time()

s = None
DIRETTA = None
SKETCH = [None]
BUCHI = []                     # (passo, messaggio)
TEMPI = []                     # (passo, secondi)
LENTO = 3.0                    # oltre: si annota come lento
F = {}                         # nome pezzo -> file


class Buco(Exception):
    pass


# ------------------------------------------------------------------------------ diretta e comandi
def servizio():
    return DIRETTA.svc if DIRETTA else Service()


def mostra(nuovo=False, key=None):
    if DIRETTA:
        DIRETTA.manda({'type': 'refresh', 'sketch': SKETCH[0], 'nuovo': nuovo, 'key': key})
        time.sleep(0.15)


def avvisa(testo, tipo=''):
    if DIRETTA:
        DIRETTA.manda({'type': 'toast', 'text': testo, 'kind': tipo})
        time.sleep(1.6 if not tipo else 3.0)


def ok(nome, *a):
    """Un comando del servizio, come lo chiama l'interfaccia. Se non riesce: Buco (il passo si ferma lì)."""
    t = time.time()
    try:
        r = getattr(s, nome)(*a)
    except Exception as ex:  # noqa: BLE001 - un'eccezione che arriva fin qui è già un buco
        raise Buco(f'{nome}: eccezione {ex!r}') from ex
    dt = time.time() - t
    TEMPI.append((nome, dt))
    if dt > LENTO:
        print(f'      (lento: {nome} {dt:.1f} s)', flush=True)
    if not r.get('ok', True):
        raise Buco(f'{nome}: {r.get("message")}')
    if DIRETTA and nome not in ('sketch_view', 'save', 'export_drawings', 'asm_export_step', 'export_dxf',
                                'export_step', 'export_bend_table', 'asm_interferences', 'import_dxf'):
        if nome in ('sketch_on_face', 'sketch_on_flat'):
            SKETCH[0] = r['sketch']
        elif nome in ('create_from_sketch', 'sheet_fold', 'sheet_tab', 'contour_flange', 'sketch_close'):
            SKETCH[0] = None
        mostra(nuovo=nome in ('new_project', 'new_assembly', 'import_dxf_create'))
    return r


def titolo(t):
    print(f'\n[{time.time() - T0:5.1f}s] {t}', flush=True)
    avvisa(t)


def passo(t):
    print(f'   · {t}', flush=True)
    avvisa(t[0].upper() + t[1:])


def prova(nome, fn, *a):
    """Esegue un passo; se non riesce lo annota e va avanti (con lo sketch chiuso, per non trascinare il guasto)."""
    try:
        return fn(*a)
    except Buco as ex:
        msg = str(ex)
    except Exception as ex:  # noqa: BLE001
        msg = f'eccezione {ex!r}\n{traceback.format_exc(limit=3)}'
    BUCHI.append((nome, msg))
    print(f'   !! BUCO in "{nome}": {msg}', flush=True)
    avvisa(f'Problema in "{nome}": {msg.splitlines()[0][:160]}', 'err')
    if SKETCH[0] and s is not None and s.asm is None:
        try:
            s.sketch_close(SKETCH[0])
        except Exception:  # noqa: BLE001
            pass
        SKETCH[0] = None
    return None


def salva(nome):
    st = s.state()
    if st['errors']:
        raise Buco(f'{nome}: il pezzo ha errori: ' + '; '.join(e['message'] for e in st['errors']))
    p = D / f'{nome}.steelcad'
    ok('save', str(p))
    F[nome] = p
    if s.result.body is not None:
        b = s.result.body
        sz = [round(x, 1) for x in bd.Shape.cast(b.shape).bounding_box().size]
        sv = [round(x, 1) for x in b.sheet.flat_size] if getattr(b, 'sheet', None) else '-'
        print(f'   = {nome}: ingombro {sz}, sviluppo {sv}, {st["bom_kg"]:.2f} kg', flush=True)
    else:
        cl = st['cutlist']
        print(f'   = {nome}: {cl["pieces"]} aste, {cl["kg"]:.1f} kg', flush=True)
    return p


def uscite(nome, lamiera=True):
    """DXF di taglio, tabella pieghe e STEP del pezzo aperto: quello che va al laser e alla piegatrice."""
    if lamiera:
        ok('export_dxf', str(D / f'{nome}.dxf'))
        ok('export_bend_table', str(D / f'{nome}_pieghe.csv'))
    ok('export_step', str(D / f'{nome}.step'))


def ingombro():
    if s.result.body is not None:
        return bd.Shape.cast(s.result.body.shape).bounding_box()
    return bd.Compound([m.solid for st in s.result.structures for m in st.members]).bounding_box()


def lamiera(nome, larg, prof, sp):
    global s
    s = servizio()
    ok('new_project', 'lamiera', {'name': nome, 'larghezza': larg, 'profondita': prof, 'spessore': sp})


def sketch(faccia):
    return ok('sketch_on_face', faccia)['sketch']


def entita_nuove(sid, prima):
    sk = s.doc.sketch(sid)
    return [k for k, e in sk.entities.items() if k not in prima and e['kind'] != 'point' and not e.get('ref')]


# ============================================================================== pezzi
GEO = {}


def banco():
    global s
    titolo('1. BANCO in tubolare 50×50×3 (modello Telaio), poi le misure cambiate dopo')
    s = servizio()
    ok('new_project', 'telaio', {'name': 'Banco', 'L': 1400, 'P': 700, 'H': 850, 'profilo': '50x50x3',
                                 'gambe': '50x50x3'})
    passo('cambio idea: lo voglio 1500 × 750 × 880, dal riquadro del modello')
    st_id = next(f['id'] for f in s.doc.features if not hasattr(f, 'constraints') and f.get('type') == 'structure')
    r = s.structure_template_apply(st_id, {'L': 1500, 'P': 750, 'H': 880})
    if r.get('ok'):
        mostra()
    else:                                          # il telaio potrebbe non nascere da un modello modificabile
        BUCHI.append(('banco: misure cambiate dopo', r.get('message')))
        avvisa(f'Problema: {r.get("message")}', 'err')
        for k, v in (('L', 1500), ('P', 750), ('H', 880)):
            ok('set_parameter', k, v)
    bb = ingombro()
    GEO['banco'] = bb
    passo(f'ingombro {bb.size.X:.0f} × {bb.size.Y:.0f} × {bb.size.Z:.0f}')
    salva('banco')
    uscite('banco', lamiera=False)


def piedino():
    global s
    titolo('2. PIEDINO: piastra 120 × 120 × 8 con foro Ø14 (modello Piastra)')
    s = servizio()
    ok('new_project', 'piastra', {'name': 'Piedino', 'larghezza': 120, 'altezza': 120, 'spessore': 8, 'foro': 14})
    salva('piedino')
    uscite('piedino', lamiera=False)
    ok('export_dxf', str(D / 'piedino.dxf'))


def piano():
    titolo('3. PIANO del banco sp. 2: flange giù da 30, angoli chiusi, serie di asole, fori per le staffe')
    bb = GEO['banco']
    W, P = round(bb.size.X + 8), round(bb.size.Y + 8)          # copre il telaio, le flange restano fuori
    GEO['piano'] = (W, P)
    lamiera('Piano banco', W, P, 2)
    for e in ('L1', 'L2', 'L3', 'L4'):
        ok('add_flange', 'SM1', e, {'length': '30', 'direction': 'down'})
    for a, b in (('FL1', 'FL2'), ('FL1', 'FL4'), ('FL3', 'FL2'), ('FL3', 'FL4')):
        ok('set_corner', 'SM1', a, b, 'over', 0.5)
    passo('asole 60 × 12 in serie: 10 colonne × 2 file, poi taglio (la prova di velocità di oggi)')
    sid = sketch('SM1/sopra')
    prima = set(s.doc.sketch(sid).entities)
    ok('sketch_add_slot', sid, [120, 120], [180, 120], 6)
    asola = entita_nuove(sid, prima)
    t = time.time()
    ok('sketch_pattern', sid, asola, 10, round((W - 300) / 9, 1), 2, P - 240)
    passo(f'serie di 20 asole in {time.time() - t:.1f} s')
    ok('create_from_sketch', sid, 'cut', {})
    passo('fori Ø8,5 per le due staffe davanti, dietro il tubo del telaio')
    sid = sketch('SM1/sopra')
    for x in (300, 340, W - 340, W - 300):
        ok('sketch_add_circle', sid, [x, 100], 4.25)
    ok('create_from_sketch', sid, 'cut', {})
    salva('piano')
    uscite('piano')


def staffa():
    titolo('4. STAFFA a L sp. 3: fori sopra e sulla flangia (due copie sotto il piano)')
    lamiera('Staffa', 80, 50, 3)
    sid = sketch('SM1/sopra')
    for x in (20, 60):
        ok('sketch_add_circle', sid, [x, 25], 4.25)
    ok('create_from_sketch', sid, 'cut', {})
    ok('add_flange', 'SM1', 'L1', {'length': '60', 'direction': 'down'})
    sid = sketch('SM1/FL1/esterno')
    for x in (20, 60):
        ok('sketch_add_circle', sid, [x, 35], 3.25)
    ok('create_from_sketch', sid, 'cut', {})
    salva('staffa')
    uscite('staffa')


def vaschetta():
    global s
    titolo('5. VASCHETTA disegnata a mano: contorno con smusso e raccordo, sp. 1,5, bordi da 50, imbutiture')
    s = servizio()
    ok('new_project', 'zero', {'name': 'Vaschetta'})
    sid = next(f.id for f in s.doc.features if hasattr(f, 'constraints'))
    SKETCH[0] = sid
    ok('sketch_add_polyline', sid, [[0, 0], [420, 0], [420, 260], [60, 260], [0, 200]], True)
    sk = s.doc.sketch(sid)
    angolo = next(k for k, e in sk.entities.items() if e['kind'] == 'point'
                  and abs(e['x'] - 420) < 1e-6 and abs(e['y'] - 260) < 1e-6)
    passo('raccordo R30 su un angolo')
    ok('sketch_fillet', sid, angolo, 30)
    ok('create_from_sketch', sid, 'sheet', {'thickness': 1.5})
    SKETCH[0] = None
    passo('bordi da 50 in su sui lati dritti')
    data = s.result.body.sheet
    lati = [e['ref'] for e in data.free_edges if e['kind'] == 'edge' and e['length'] > 50]
    fatte = 0
    for e in lati:
        r = s.add_flange('SM1', e, {'length': '50'})
        if r.get('ok'):
            fatte += 1
            mostra()
        else:
            BUCHI.append((f'vaschetta: flangia su {e}', r.get('message')))
            print(f'   !! flangia su {e}: {r.get("message")}', flush=True)
    passo(f'{fatte} flange su {len(lati)} lati')
    passo('quattro imbutiture Ø40 profonde 4 sul fondo')
    sid = sketch('SM1/sopra')
    for x, y in ((100, 80), (300, 80), (100, 180), (300, 180)):
        ok('sketch_add_circle', sid, [x, y], 20)
    ok('create_from_sketch', sid, 'dimple', {'depth': 4})
    salva('vaschetta')
    uscite('vaschetta')


def carter():
    titolo('6. CARTER posteriore sp. 1,5: piega su linea, orlo, linguetta, persiane')
    lamiera('Carter', 700, 500, 1.5)
    passo('piega su linea sullo sviluppo, a 380 dal bordo')
    sid = ok('sketch_on_flat', 'SM1')['sketch']
    ok('sketch_add_polyline', sid, [[-5, 380], [705, 380]], False)
    ok('sheet_fold', sid, 90, 'up')
    passo('orlo chiuso da 10 in cima alla parte piegata')
    ok('add_flange', 'SM1', None, {'length': '10', 'angle': 180, 'direction': 'up'}, 'PL1')
    passo('linguetta di fissaggio sul bordo davanti')
    sid = sketch('SM1/sopra')
    ok('sketch_add_polyline', sid, [[300, 0], [300, -40], [400, -40], [400, 0]], False)
    ok('sheet_tab', sid)
    passo('sei persiane 80 × 8 per l’aria')
    sid = sketch('SM1/sopra')
    for k in range(6):
        x = 120 + k * 80
        ok('sketch_add_polyline', sid, [[x, 120], [x + 60, 120]], False)
    ok('create_from_sketch', sid, 'louver', {'width': 12, 'height': 5})
    salva('carter')
    uscite('carter')


def cappa():
    global s
    titolo('7. CAPPA: raccordo quadro-tondo 800 × 500 → Ø250, eccentrico, sp. 1,5, a pieghe')
    s = servizio()
    ok('new_project', 'tramoggia', {'name': 'Cappa', 'A': 800, 'B': 500, 'D': 250, 'H': 350, 'ex': 0, 'ey': 60,
                                    'spessore': 1.5})
    info = s.result.body.sheet.shape_info
    passo(f'{info["pieghe"]} pieghe, la più forte {info["angolo_max"]:.1f}°')
    passo('cambio misure dal modello: altezza 400')
    fid = next(f['id'] for f in s.doc.features if not hasattr(f, 'constraints') and f.get('type') == 'sheet_shape')
    ok('structure_template_apply', fid, {'H': 400})
    salva('cappa')
    uscite('cappa')
    titolo('8. CAMINO: tronco di cono calandrato Ø250 → Ø160, alto 200')
    s = servizio()
    ok('new_project', 'cono', {'name': 'Camino', 'D1': 250, 'D2': 160, 'H': 200, 'spessore': 1.5,
                               'riferimento': 'interno', 'modo': 'rolled'})
    salva('camino')
    uscite('camino')


def portale():
    global s
    titolo('9. PORTALE da disegno che regge la cappa: scheletro a mano, ripetuto in profondità e collegato')
    s = servizio()
    bb = GEO['banco']
    L, H = round(bb.size.X + 300), 2000
    ok('new_project', 'disegno', {'name': 'Portale', 'piano': 'XZ'})
    sid = next(f.id for f in s.doc.features if hasattr(f, 'constraints'))
    SKETCH[0] = sid
    ok('sketch_add_polyline', sid, [[0, 0], [0, H], [L, H], [L, 0]], False)
    ok('create_from_sketch', sid, 'structure', {'profile': '60x60x3', 'copies': 2, 'distance': round(bb.size.Y + 200),
                                                'connect': True, 'connect_profile': '60x40x3'})
    SKETCH[0] = None
    salva('portale')
    uscite('portale', lamiera=False)


def scaffale_e_cancello():
    global s
    titolo('10. SCAFFALE di fianco al banco (5 ripiani) e CANCELLO di protezione')
    s = servizio()
    ok('new_project', 'scaffale', {'name': 'Scaffale', 'L': 1000, 'P': 400, 'H': 1800, 'ripiani': 4})
    passo('un ripiano in più, dal modello')
    st_id = next(f['id'] for f in s.doc.features if not hasattr(f, 'constraints') and f.get('type') == 'structure')
    ok('structure_template_apply', st_id, {'ripiani': 5})
    salva('scaffale')
    uscite('scaffale', lamiera=False)
    s = servizio()
    ok('new_project', 'cancello', {'name': 'Cancello', 'L': 1200, 'H': 1100, 'telaio': '40x40x3', 'sbarre': '20x20x2',
                                   'passo': 110})
    salva('cancello')
    uscite('cancello', lamiera=False)


def canalina():
    global s
    titolo('11. CANALINA importata dal DXF dello sviluppo (sp. 2, pieghe a 90°)')
    s = servizio()
    r = ok('import_dxf', str(QUI / 'test_parts' / 'sheetmetal_u_2mm' / 'canalina_sviluppo.dxf'))
    giro = r.get('scelto') if r.get('scelto') is not None else 0
    pieghe = r.get('giro', {}).get('pieghe', [])
    passo(f'{len(r["giri"])} contorni nel disegno, {len(pieghe)} linee di piega sul pezzo')
    ok('import_dxf_create', giro, {'name': 'Canalina', 'thickness': 2, 'material': 'S235',
                                   'bends': [{'angle': 90, 'direction': 'up'} for _ in pieghe]})
    salva('canalina')
    uscite('canalina')


# ============================================================================== assieme
def posa(iid, R, minimo):
    """Gira l'istanza (R) e la sposta perché il suo ingombro parta da `minimo` (coordinate dell'assieme)."""
    i = s.asm.instance(iid)
    part = s.asm_parts[i['file']]
    R = np.array(R, dtype=float)
    bb = A.placed_shape(part, R.tolist(), [0, 0, 0]).bounding_box()
    T = np.array(minimo, dtype=float) - np.array([bb.min.X, bb.min.Y, bb.min.Z])

    def fn():
        i['R'], i['T'] = R.tolist(), T.tolist()
    r = s._asm_change(f'Posa {iid}', fn)
    if not r.get('ok'):
        raise Buco(f'posa {iid}: {r.get("message")}')
    mostra()


def bb_ist(iid):
    i = s.asm.instance(iid)
    return A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()


def faccia(iid, nome=None, kind='piana', vicino=None, r=None):
    best = None
    for o in s.scene()['objects']:
        if o['id'] != iid:
            continue
        for f in o['faces']:
            inf = s._asm_face(iid, f['index'])
            if inf['kind'] != kind or (nome and inf['name'] != nome) or (r and abs(inf.get('r', 0) - r) > 1e-3):
                continue
            d = np.linalg.norm(np.array(inf['p']) - np.array(vicino)) if vicino is not None else 0
            if best is None or d < best[0]:
                best = (d, f['index'])
    if best is None:
        raise Buco(f'faccia non trovata: {iid} {nome or kind}')
    return best[1]


def mate(tipo, a, b, offset=0, flip=False):
    return ok('asm_add_mate', tipo, {'inst': a[0], 'face': a[1]}, {'inst': b[0], 'face': b[1]}, offset, flip)


def assieme():
    global s
    titolo('12. ASSIEME: la postazione montata')
    s = servizio()
    ok('new_assembly', 'Postazione con cappa')
    ordine = [('banco', 'Banco'), ('piedino', 'Piedino 1'), ('piedino', 'Piedino 2'), ('piedino', 'Piedino 3'),
              ('piedino', 'Piedino 4'), ('piano', 'Piano'), ('staffa', 'Staffa sinistra'), ('staffa', 'Staffa destra'),
              ('vaschetta', 'Vaschetta'), ('carter', 'Carter'), ('portale', 'Portale'), ('cappa', 'Cappa'),
              ('camino', 'Camino'), ('scaffale', 'Scaffale'), ('cancello', 'Cancello'), ('canalina', 'Canalina')]
    ids = {}
    for k, nome in ordine:
        if k not in F:
            BUCHI.append((f'assieme: {nome}', 'il pezzo non è stato creato, lo salto'))
            continue
        r = prova(f'inserisci {nome}', ok, 'asm_insert', str(F[k]))
        if r:
            iid = s.asm.instances[-1]['id']
            prova(f'nome {nome}', ok, 'asm_set', iid, {'name': nome})
            ids[nome] = iid
    I3 = np.eye(3)
    if 'Banco' in ids:
        prova('banco fermo', ok, 'asm_set', ids['Banco'], {'fixed': True})

    def montaggio_banco():
        passo('piedini sotto le gambe, banco sopra i piedini')
        bb = bb_ist(ids['Banco'])
        dz = 8 - bb.min.Z
        prova('banco su', ok, 'asm_move', ids['Banco'], 0, 0, dz)
        bb = bb_ist(ids['Banco'])
        for k, (x, y) in enumerate(((bb.min.X, bb.min.Y), (bb.max.X - 50, bb.min.Y), (bb.min.X, bb.max.Y - 50),
                                    (bb.max.X - 50, bb.max.Y - 50)), 1):
            if f'Piedino {k}' in ids:
                posa(ids[f'Piedino {k}'], I3, [x + 25 - 60, y + 25 - 60, 0])
        return bb

    bb = prova('banco e piedini', montaggio_banco)
    if bb is None:
        return ids

    def montaggio_piano():
        passo('piano sopra il telaio, con le flange che scendono fuori dai tubi')
        W, P = GEO['piano']
        posa(ids['Piano'], I3, [bb.min.X - (W - bb.size.X) / 2, bb.min.Y - (P - bb.size.Y) / 2, bb.max.Z - 30 + 2])
        # il piano: fisso anche lui, le staffe si accoppiano a lui
        ok('asm_set', ids['Piano'], {'fixed': True})

    prova('piano', montaggio_piano)

    def staffe():
        passo('staffe sotto il piano: faccia su faccia e foro su foro (accoppiamenti)')
        for nome, xs in (('Staffa sinistra', (300, 340)), ('Staffa destra', None)):
            iid = ids[nome]
            if xs is None:
                W = GEO['piano'][0]
                xs = (W - 340, W - 300)
            mate('faccia', (ids['Piano'], faccia(ids['Piano'], 'SM1/sotto')), (iid, faccia(iid, 'SM1/sopra')))
            for xp, xstaffa in zip(xs, (20, 60)):
                mate('asse', (ids['Piano'], faccia(ids['Piano'], None, 'cilindrica', [xp, 100, 1], r=4.25)),
                     (iid, faccia(iid, None, 'cilindrica', [xstaffa, 25, 1.5], r=4.25)))
        avv = s.state()['warnings']
        if avv:
            raise Buco('accoppiamenti con avvisi: ' + '; '.join(avv))

    prova('staffe', staffe)

    def resto():
        top = bb_ist(ids['Piano']).max.Z
        passo('vaschetta e carter sul piano')
        posa(ids['Vaschetta'], I3, [bb.min.X + 150, bb.min.Y + 150, top])
        posa(ids['Carter'], I3, [bb.max.X - 800, bb.min.Y + 100, top])
        passo('portale a cavallo del banco, cappa appesa sotto la traversa, camino sopra')
        pb = bb_ist(ids['Portale'])
        posa(ids['Portale'], I3, [bb.min.X - (pb.size.X - bb.size.X) / 2, bb.min.Y - (pb.size.Y - bb.size.Y) / 2, 0])
        pb = bb_ist(ids['Portale'])
        cb = A.placed_shape(s.asm_parts[s.asm.instance(ids['Cappa'])['file']], I3.tolist(), [0, 0, 0]).bounding_box()
        posa(ids['Cappa'], I3, [pb.center().X - cb.size.X / 2, pb.center().Y - cb.size.Y / 2, pb.max.Z - 60 - cb.size.Z])
        kb = bb_ist(ids['Cappa'])
        # il camino sul tondo della cappa: il tondo è spostato di ey = 60 verso il fondo
        cam = A.placed_shape(s.asm_parts[s.asm.instance(ids['Camino'])['file']], I3.tolist(), [0, 0, 0]).bounding_box()
        posa(ids['Camino'], I3, [kb.center().X - cam.size.X / 2, kb.center().Y + 60 - cam.size.Y / 2, kb.max.Z])
        passo('scaffale a destra, cancello di protezione a sinistra (girato lungo il fianco), canalina sotto il piano')
        posa(ids['Scaffale'], I3, [pb.max.X + 150, bb.min.Y, 0])
        posa(ids['Cancello'], [[0, -1, 0], [1, 0, 0], [0, 0, 1]], [pb.min.X - 250, bb.min.Y, 0])
        posa(ids['Canalina'], I3, [bb.min.X + 400, bb.center().Y, 300])
        mostra(nuovo=True)

    prova('posizionamento', resto)
    return ids


def controlli():
    titolo('13. CONTROLLI: interferenze, distinta, tavole, STEP')
    t = time.time()
    inter = ok('asm_interferences').get('interferences', [])
    passo(f'interferenze in {time.time() - t:.1f} s: ' + ('nessuna' if not inter else
                                                           '; '.join(x['label'] for x in inter[:6])))
    if inter:
        BUCHI.append(('interferenze', '; '.join(x['label'] for x in inter)))
    righe = A.bom(s.asm, s.asm_parts)
    print('   DISTINTA')
    tot = 0
    for k, r in enumerate(righe, 1):
        print(f'   {k:2d}  {r["name"]:<22} {r["qty"]:>2} ×  {r["material"]:<6} sp. {r["thickness"] or "":<4} '
              f'{r["mass_tot"]:8.2f} kg')
        tot += r['mass_tot']
    print(f'       {"totale":<22}{"":>27}{tot:8.2f} kg')
    ok('save', str(D / 'postazione.steelcad-asm'))
    campi = {'azienda': 'Prova SteelCAD', 'disegnatore': 'SteelCAD', 'numero': 'PO-1500', 'revisione': 'A',
             'note': 'Vetrina: postazione con cappa', 'formato': 'A3'}
    t = time.time()
    r = ok('export_drawings', str(D / 'postazione_tavole.pdf'), campi, True)
    passo(f'{r["message"]} ({time.time() - t:.0f} s)')
    r = ok('asm_export_step', str(D / 'postazione.step'))
    passo(r.get('message') or 'STEP salvato')
    return inter, tot


def main():
    global DIRETTA
    if LIVE:
        spec = importlib.util.spec_from_file_location('vetrina_quadro', QUI / 'tools' / 'vetrina_quadro.py')
        vq = importlib.util.module_from_spec(spec)
        sys.argv = [sys.argv[0], str(D)]
        spec.loader.exec_module(vq)
        vq.D = D

        class Diretta(vq.Diretta):
            def apri(self):
                import glob
                import subprocess
                import webbrowser
                chrome = next(iter(glob.glob(r'C:\Program Files*\Google\Chrome\Application\chrome.exe')), None)
                if chrome:
                    subprocess.Popen([chrome, '--new-window', '--start-maximized', self.url])
                else:
                    webbrowser.open(self.url)
                print(f'Diretta su {self.url} - aspetto il browser...', flush=True)
                self.manda({'type': 'toast', 'text': 'Diretta SteelCAD: postazione con cappa, tutte le funzioni'})
                time.sleep(2)
        DIRETTA = Diretta(5152)
        DIRETTA.apri()
    for nome, fn in (('banco', banco), ('piedino', piedino), ('piano', piano), ('staffa', staffa),
                     ('vaschetta', vaschetta), ('carter', carter), ('cappa e camino', cappa), ('portale', portale),
                     ('scaffale e cancello', scaffale_e_cancello), ('canalina', canalina)):
        prova(nome, fn)
    prova('assieme', assieme)
    esito = prova('controlli', controlli) or ([], 0)
    print(f'\nFatto in {time.time() - T0:.0f} s. File in {D}')
    lenti = sorted(((n, t) for n, t in TEMPI if t > LENTO), key=lambda x: -x[1])
    if lenti:
        print('PASSI LENTI (> 3 s):')
        for n, t in lenti:
            print(f'   {t:6.1f} s  {n}')
    print(f'BUCHI TROVATI: {len(BUCHI)}')
    for n, m in BUCHI:
        print(f' - {n}: {m}')
    if DIRETTA:
        mostra(key='0')
        DIRETTA.manda({'type': 'toast', 'text': f'Fatto in {time.time() - T0:.0f} s: {len(F)} pezzi, {esito[1]:.0f} kg, '
                       f'{len(BUCHI)} problemi trovati (li sto guardando)', 'kind': 'err' if BUCHI else ''})
        print('La pagina resta viva: chiudi questa finestra (Ctrl+C) quando hai finito di guardare.', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
