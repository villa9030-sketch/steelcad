"""Prova di carico in diretta: un impianto di scarico con tramoggia, bocca inclinata, cabina elettrica e cappa.

    python tools/vetrina_impianto.py [cartella]          (di default Documenti/SteelCAD/vetrina_impianto)
    python tools/vetrina_impianto.py --live [cartella]   in diretta: si apre Chrome e si vede crescere ogni pezzo

Regola di questa vetrina (20/10, Stefano): solo comandi che l'utente ha davanti. Ogni passo chiama il servizio
come lo chiama l'interfaccia, e prima si controlla che quel comando sia raggiungibile da un pulsante o da un
pannello dell'app (app.js → ponte main.py → servizio). Uno che non lo è si annota come COMANDO NASCOSTO.
Niente scorciatoie interne: anche nell'assieme i pezzi si mettono a posto con Sposta e Ruota.

Pezzi: telaio di sostegno (modello Telaio, un'asta cambiata), tramoggia con cassone (scarico spostato), bocca
(raccordo quadro-tondo eccentrico) con il tronchetto calandrato montato inclinato, cabina elettrica (cassa con
bordi, angoli, fori filettati M6, asole in serie, foro esagonale, persiane; porta con orlo, imbutiture, foro svasato,
linguetta), mensola disegnata (struttura da sketch), cappa (raccordo) con camino (cono calandrato), deflettore
piegato a colpi (bumping con raggio e bumping a linee). Poi assieme con accoppiamenti, interferenze, distinta,
tavole, STEP, DXF e «Prepara per il laser».
"""
import ast
import importlib.util
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path

QUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(QUI))
import build123d as bd  # noqa: E402

from app.service import Service  # noqa: E402
from cad_engine import assembly as A  # noqa: E402

LIVE = '--live' in sys.argv
_arg = [a for a in sys.argv[1:] if not a.startswith('--')]
D = Path(_arg[0]) if _arg else Path(os.path.expanduser('~')) / 'Documents' / 'SteelCAD' / 'vetrina_impianto'
os.environ.setdefault('STEELCAD_HOME', __import__('tempfile').mkdtemp(prefix='steelcad_vetrina_'))
D.mkdir(parents=True, exist_ok=True)
T0 = time.time()
if not Service().bend_default().get('radius'):
    os.environ['STEELCAD_RULES'] = str(D / 'regole_vetrina.json')
    Service().set_bend_default({'radius': 1, 'method': 'k', 'k': 0.21})


# ------------------------------------------------------------------ quali comandi ha davanti l'utente
def comandi_visibili() -> dict:
    """Comando del servizio → il comando dell'interfaccia (ponte) che lo chiama. Si legge app.js (le stringhe dei
    comandi che i pulsanti mandano) e main.py (cosa fa ogni comando del ponte sul servizio)."""
    js = (QUI / 'app/ui/app.js').read_text(encoding='utf-8')
    usati = set(re.findall(r"'([a-z_0-9]+)'", js))
    albero = ast.parse((QUI / 'app/main.py').read_text(encoding='utf-8'))
    out = {}
    for cl in [n for n in albero.body if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cl.body if isinstance(n, ast.FunctionDef)]:
            if fn.name not in usati:
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and n.value.attr == '_svc':
                    out.setdefault(n.attr, fn.name)
    return out


VISIBILI = comandi_visibili()
s = None
DIRETTA = None
SKETCH = [None]
BUCHI, NASCOSTI, TEMPI, USATI = [], [], [], {}
LENTO = 3.0
F = {}
GEO = {}


class Buco(Exception):
    pass


def servizio():
    return DIRETTA.svc if DIRETTA else Service()


def mostra(nuovo=False, key=None):
    if DIRETTA:
        DIRETTA.manda({'type': 'refresh', 'sketch': SKETCH[0], 'nuovo': nuovo, 'key': key})
        time.sleep(0.12)


def avvisa(testo, tipo=''):
    if DIRETTA:
        DIRETTA.manda({'type': 'toast', 'text': testo, 'kind': tipo})
        time.sleep(1.4 if not tipo else 2.6)


def ok(nome, *a):
    """Un comando, come lo manda l'interfaccia. Prima: è un comando che l'utente ha davanti? Se no, NASCOSTO."""
    if nome not in VISIBILI:
        if nome not in [n for n, _ in NASCOSTI]:
            NASCOSTI.append((nome, 'nessun pulsante o pannello lo chiama'))
            print(f'   ?? COMANDO NASCOSTO: {nome}', flush=True)
    USATI[nome] = USATI.get(nome, 0) + 1
    t = time.time()
    try:
        r = getattr(s, nome)(*a)
    except Exception as ex:  # noqa: BLE001
        raise Buco(f'{nome}: eccezione {ex!r}') from ex
    dt = time.time() - t
    TEMPI.append((nome, dt))
    if dt > LENTO:
        print(f'      (lento: {nome} {dt:.1f} s)', flush=True)
    if not r.get('ok', True):
        raise Buco(f'{nome}: {r.get("message")}')
    if DIRETTA and nome not in ('sketch_view', 'save', 'export_drawings', 'asm_export_step', 'export_dxf',
                                'export_step', 'export_bend_table', 'asm_interferences', 'prepara', 'prepara_info'):
        if nome in ('sketch_on_face', 'sketch_on_flat', 'new_project') and r.get('sketch'):
            SKETCH[0] = r['sketch']
        elif nome in ('create_from_sketch', 'sheet_fold', 'sheet_tab', 'contour_flange', 'sketch_close'):
            SKETCH[0] = None
        mostra(nuovo=nome in ('new_project', 'new_assembly'))
    return r


def titolo(t):
    print(f'\n[{time.time() - T0:5.1f}s] {t}', flush=True)
    avvisa(t)


def passo(t):
    print(f'   · {t}', flush=True)
    avvisa(t[0].upper() + t[1:])


def prova(nome, fn, *a):
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


def salva(nome, lamiera=True):
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
    if lamiera:
        prova(f'{nome}: DXF', ok, 'export_dxf', str(D / f'{nome}.dxf'))
        prova(f'{nome}: tabella pieghe', ok, 'export_bend_table', str(D / f'{nome}_pieghe.csv'))
    prova(f'{nome}: STEP', ok, 'export_step', str(D / f'{nome}.step'))
    return p


def nuovo(kind, valori):
    global s
    s = servizio()
    return ok('new_project', kind, valori)


def sketch(faccia):
    r = ok('sketch_on_face', faccia)
    SKETCH[0] = r['sketch']
    mostra()
    return r['sketch']


def nuove(sid, prima, kind=None):
    sk = s.doc.sketch(sid)
    return [k for k, e in sk.entities.items() if k not in prima and e['kind'] != 'point' and not e.get('ref')
            and (kind is None or e['kind'] == kind)]


def entita(sid):
    return set(s.doc.sketch(sid).entities)


def foro_cliccato(nome_faccia_parete, spec, tutti=True):
    """Come l'utente: clic sulla parete di un foro sul pezzo, a destra il tipo, Applica."""
    facce = [x for x in s.scene()['objects'][0]['faces'] if x['name'] == nome_faccia_parete]
    if not facce:
        raise Buco(f'nessun foro con parete {nome_faccia_parete}')
    sel = ok('select', 'body', facce[0]['index'], facce[0]['name'])['selection']
    fo = sel.get('foro')
    if not fo:
        raise Buco('cliccando la parete del foro non si apre il pannello del foro')
    ok('sketch_hole_type', fo['sketch'], fo['uguali'] if tutti else [fo['cerchio']], spec)
    return fo


def flangia(lato, lungh, **k):
    r = ok('add_flange', 'SM1', lato, {'length': str(lungh), **{a: str(b) for a, b in k.items()}})
    return s._sheet_def('SM1')['flanges'][-1]['id'], r


def su_punta(madre, lungh, **k):
    ok('add_flange', 'SM1', None, {'length': str(lungh), **{a: str(b) for a, b in k.items()}}, madre)
    return s._sheet_def('SM1')['flanges'][-1]['id']


# ============================================================================== pezzi
def telaio():
    titolo('1. TELAIO di sostegno in tubolare 60×60×3 (modello Telaio)')
    nuovo('telaio', {'name': 'Telaio', 'L': 1300, 'P': 1100, 'H': 1500, 'profilo': '60x60x3', 'gambe': '60x60x3'})
    passo('cambio idea dal riquadro del modello: un po’ più alto, 1600')
    st_id = next(f['id'] for f in s.doc.features if not hasattr(f, 'constraints') and f.get('type') == 'structure')
    ok('structure_template_apply', st_id, {'H': 1600})
    passo('una gamba più robusta: clic sull’asta, tubo 80×80×4 (solo quella)')
    st = s.result.structures[0]
    gamba = next(m for m in st.members if abs(m.start.Z - m.end.Z) > 1000)
    ok('select', f'{st.id}/{gamba.id}')
    ok('edit_member', f'{st.id}/{gamba.id}', {'profile': '80x80x4'}, False)
    b = bd.Compound([m.solid for st in s.result.structures for m in st.members]).bounding_box()
    GEO['telaio'] = b
    salva('telaio', lamiera=False)


def tramoggia():
    titolo('2. TRAMOGGIA con cassone, scarico spostato di 120 mm, bordo in alto e flangia allo scarico')
    nuovo('tramoggia_cassone', {'name': 'Tramoggia', 'A': 1100, 'B': 900, 'Hc': 500, 'a': 300, 'b': 300, 'Ht': 700,
                                'ex': 120, 'ey': 0, 'bordo': 40, 'angoli_bordo': 'aperti', 'flangia': 40, 'smusso': 0,
                                'spessore': 3, 'riferimento': 'esterno', 'divisione': 'auto', 'foglio': '1500x3000'})
    sel = ok('select', 'body')['selection']
    forma = sel.get('forma') or {}
    passo(f'divisa in {forma.get("pezzi", "?")} pezzi, {forma.get("pieghe", "?")} pieghe, '
          f'saldature {forma.get("saldature_m", "?")} m')
    salva('tramoggia')


def bocca():
    titolo('3. BOCCA: raccordo quadro-tondo 300×300 → Ø220, tondo spostato (eccentrico)')
    nuovo('tramoggia', {'name': 'Bocca', 'A': 300, 'B': 300, 'D': 220, 'H': 260, 'ex': 50, 'ey': 0, 'spessore': 2,
                        'rif_base': 'esterno', 'rif_tondo': 'esterno'})
    salva('bocca')
    titolo('3b. TRONCHETTO calandrato Ø220 → Ø200 (andrà montato inclinato di 25°)')
    nuovo('cono', {'name': 'Tronchetto', 'D1': 220, 'D2': 200, 'H': 250, 'spessore': 2, 'modo': 'rolled',
                   'riferimento': 'esterno'})
    salva('tronchetto')


def cabina():
    titolo('4. CABINA ELETTRICA: cassa 500×300, profonda 250, sp 1,5')
    nuovo('lamiera', {'name': 'Cassa cabina', 'larghezza': 500, 'profondita': 300, 'spessore': 1.5})
    passo('le quattro pareti da 250, poi un bordo da 20 verso dentro su ognuna')
    pareti = {}
    for lato in ('L1', 'L2', 'L3', 'L4'):
        fid, _ = flangia(lato, 250)
        pareti[lato] = fid
    for lato, fid in pareti.items():
        prova(f'bordo su {fid}', lambda f=fid: su_punta(f, 20, direction='down'))
    passo('angoli: le pareti di fianco vanno sopra quelle davanti e dietro')
    for a, b in (('L1', 'L2'), ('L2', 'L3'), ('L3', 'L4'), ('L4', 'L1')):
        prova(f'angolo {a}/{b}', ok, 'set_corner', 'SM1', pareti[a], pareti[b], 'over', 0.5)

    def fondo():
        passo('sul fondo: 4 fori per la piastra, che poi faccio filettati M6 cliccandoli')
        sid = sketch('SM1/sopra')
        for x, y in ((60, 60), (440, 60), (60, 240), (440, 240)):
            ok('sketch_add_circle', sid, [x, y], 3)
        passo('uscita cavi: un’asola e la serie di 3, un foro esagonale, una finestra con gli angoli raccordati')
        prima = entita(sid)
        ok('sketch_add_slot', sid, [150, 40], [190, 40], 6)
        asola = nuove(sid, prima)
        ok('sketch_pattern', sid, asola, 3, 70, 1, 0)
        ok('sketch_add_polygon', sid, [250, 150], [262, 150], 6)
        prima = entita(sid)
        ok('sketch_add_rectangle', sid, [180, 200], [320, 250])
        lati = nuove(sid, prima, 'line')
        ok('sketch_dimension', sid, 'length', [lati[0]])          # la quota c'è già: si riprende quella
        sk = s.doc.sketch(sid)
        angolo = sk.entities[lati[0]]['a']
        ok('sketch_fillet', sid, angolo, 8)
        ok('create_from_sketch', sid, 'cut', {})
        SKETCH[0] = None
        foro_cliccato('TG1/parete', {'tipo': 'filettato', 'M': 'M6'})

    prova('fondo della cassa', fondo)

    def persiane():
        passo('persiane sul fianco destro per l’aria')
        sid = sketch(f'SM1/{pareti["L2"]}/esterno')
        v = ok('sketch_view', sid)['sketch']
        xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']; ys = [p['xy'][1] for p in v['points'] if p['id'] != 'O']
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        for k in range(4):
            y = y0 + (y1 - y0) * (0.3 + 0.12 * k)
            ok('sketch_add_polyline', sid, [[x0 + (x1 - x0) * 0.25, y], [x0 + (x1 - x0) * 0.75, y]], False)
        ok('create_from_sketch', sid, 'louver', {'width': 8, 'height': 4})
        SKETCH[0] = None

    prova('persiane', persiane)
    salva('cassa_cabina')

    titolo('4b. PORTA della cabina: 500×300 con battuta, orlo, imbutiture e foro svasato per la maniglia')
    nuovo('lamiera', {'name': 'Porta cabina', 'larghezza': 500, 'profondita': 300, 'spessore': 1.5})
    bat = {}
    for lato in ('L1', 'L2', 'L3', 'L4'):
        bat[lato], _ = flangia(lato, 18, direction='down')
    prova('orlo sulla battuta davanti', lambda: su_punta(bat['L1'], 8, angle=180))

    def maniglia():
        passo('due imbutiture per irrigidire e il foro svasato della maniglia')
        sid = sketch('SM1/sopra')
        ok('sketch_add_circle', sid, [120, 150], 20)
        prima = entita(sid)
        ok('sketch_add_circle', sid, [380, 150], 20)
        ok('create_from_sketch', sid, 'dimple', {'depth': 4})
        SKETCH[0] = None
        sid = sketch('SM1/sopra')
        ok('sketch_add_circle', sid, [250, 60], 3.25)
        ok('create_from_sketch', sid, 'cut', {})
        SKETCH[0] = None
        nome = next(x['name'] for x in s.scene()['objects'][0]['faces'] if (x['name'] or '').endswith('/parete'))
        passo('prima provo una svasatura troppo grande (Ø12 su lamiera da 1,5): deve rifiutarla e lasciare il pezzo com’era')
        try:
            foro_cliccato(nome, {'tipo': 'svasato', 'D': 12, 'angolo': 90})
            BUCHI.append(('svasatura troppo profonda', 'accettata: doveva essere rifiutata'))
        except Buco as ex:
            passo(f'rifiutata, giusto: {str(ex).split(": ", 1)[-1][:90]}')
        if s.state()['errors']:
            raise Buco('dopo il rifiuto il pezzo è rimasto in errore')
        foro_cliccato(nome, {'tipo': 'svasato', 'D': 8, 'angolo': 90})

    prova('maniglia', maniglia)

    def linguetta():
        passo('una linguetta per la cerniera, disegnata sulla battuta sinistra')
        sid = sketch(f'SM1/{bat["L4"]}/esterno')
        v = ok('sketch_view', sid)['sketch']
        xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']; ys = [p['xy'][1] for p in v['points'] if p['id'] != 'O']
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        xm = (x0 + x1) / 2
        # la linguetta va sul bordo libero della battuta (non su quello della piega): si prova da un lato, poi dall'altro
        for y, h in ((y1, 25), (y0, -25)):
            prima = entita(sid)
            ok('sketch_add_polyline', sid, [[xm - 30, y], [xm - 30, y + h], [xm + 30, y + h], [xm + 30, y]], False)
            r = s.sheet_tab(sid)
            USATI['sheet_tab'] = USATI.get('sheet_tab', 0) + 1
            if r.get('ok'):
                mostra()
                break
            passo(f'da questa parte no ({r.get("message", "")[:70]}): provo il bordo opposto')
            ok('sketch_delete', sid, nuove(sid, prima))
        else:
            raise Buco('sheet_tab: ' + r.get('message', ''))
        SKETCH[0] = None

    prova('linguetta', linguetta)
    salva('porta_cabina')


def mensola():
    titolo('5. MENSOLA della cabina: struttura disegnata (sketch) in tubo 40×40×3')
    nuovo('disegno', {'name': 'Mensola', 'piano': 'XZ'})
    sid = SKETCH[0] or s.state()['tree']['children'][0].get('ref')
    sid = next(f.id for f in s.doc.features if hasattr(f, 'entities'))
    ok('sketch_add_polyline', sid, [[0, 0], [0, 400], [350, 400]], False)
    ok('sketch_add_polyline', sid, [[0, 120], [350, 400]], False)
    ok('create_from_sketch', sid, 'structure', {'profile': '40x40x3', 'copies': 2, 'distance': 300, 'side': 'back',
                                                'connect': True, 'connect_profile': '40x20x2', 'connect_group': 'Traversi'})
    SKETCH[0] = None
    salva('mensola', lamiera=False)


def cappa():
    titolo('6. CAPPA d’aspirazione: raccordo 700×500 → Ø250, tondo spostato verso il muro')
    nuovo('tramoggia', {'name': 'Cappa', 'A': 700, 'B': 500, 'D': 250, 'H': 320, 'ex': 0, 'ey': 70, 'spessore': 1.5,
                        'rif_base': 'esterno', 'rif_tondo': 'esterno'})
    salva('cappa')
    titolo('6b. CAMINO: cono calandrato Ø250 → Ø180')
    nuovo('cono', {'name': 'Camino', 'D1': 250, 'D2': 180, 'H': 300, 'spessore': 1.5, 'modo': 'rolled',
                   'riferimento': 'esterno'})
    salva('camino')


def deflettore():
    titolo('7. DEFLETTORE sotto la cappa: lamiera 600×400, piegata a colpi (bumping)')
    nuovo('lamiera', {'name': 'Deflettore', 'larghezza': 600, 'profondita': 400, 'spessore': 2})

    def a_raggio():
        passo('bumping «a raggio»: una linea, 10 colpi, raggio grande 150, 60° in tutto')
        sid = sketch('SM1/sopra')
        ok('sketch_add_polyline', sid, [[0, 120], [600, 120]], False)
        ok('sheet_fold', sid, 6, 'up', False, {'colpi': 10, 'raggio': 150})
        SKETCH[0] = None

    prova('bumping a raggio', a_raggio)

    def a_linee():
        passo('bumping «a linee»: 6 linee disegnate, una per colpo, 90° in tutto dall’altra parte')
        sid = sketch('SM1/sopra')
        v = ok('sketch_view', sid)['sketch']
        xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']; ys = [p['xy'][1] for p in v['points'] if p['id'] != 'O']
        x0, x1, y1 = min(xs), max(xs), max(ys)
        for k in range(6):                         # dalla parte opposta a quella già piegata
            y = y1 - 60 - 8 * k
            ok('sketch_add_polyline', sid, [[x0, y], [x1, y]], False)
        ok('sheet_fold', sid, 15, 'down', False)
        SKETCH[0] = None

    prova('bumping a linee', a_linee)

    def accorcia():
        passo('accorcio il deflettore: due linee da bordo a bordo, «Togli materiale» toglie i due pezzi')
        sid = sketch('SM1/sopra')
        v = ok('sketch_view', sid)['sketch']
        xs = [p['xy'][0] for p in v['points'] if p['id'] != 'O']; ys = [p['xy'][1] for p in v['points'] if p['id'] != 'O']
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        for x in (x0 + 30, x1 - 30):
            ok('sketch_add_polyline', sid, [[x, y0], [x, y1]], False)
        ok('create_from_sketch', sid, 'cut', {})
        SKETCH[0] = None

    prova('accorcia', accorcia)
    righe = s.result.body.sheet.summary()['bends'] if s.result.body is not None else []
    passo(f'tabella pieghe: {len(righe)} pieghe, in ordine: ' + ', '.join(r['flange'] for r in righe[:8]) + ('…' if len(righe) > 8 else ''))
    salva('deflettore')


# ============================================================================== assieme (solo Sposta e Ruota)
def bb_ist(iid):
    i = s.asm.instance(iid)
    return A.placed_shape(s.asm_parts[i['file']], i['R'], i['T']).bounding_box()


def metti(iid, minimo=None, centro=None, rot=()):
    """Come l'utente: Ruota (asse, gradi) e poi Sposta di quanto serve perché l'ingombro parta da `minimo` (o abbia il
    centro in `centro`). Nessun accesso diretto alla posizione."""
    if iid is None:
        return
    for asse, g in rot:
        ok('asm_rotate', iid, asse, g)
    b = bb_ist(iid)
    if centro is not None:
        d = [centro[0] - b.center().X, centro[1] - b.center().Y, centro[2] - b.center().Z]
    else:
        d = [minimo[0] - b.min.X, minimo[1] - b.min.Y, minimo[2] - b.min.Z]
    ok('asm_move', iid, *[round(x, 3) for x in d])


def assieme():
    global s
    titolo('8. ASSIEME: l’impianto montato (solo Sposta, Ruota e accoppiamenti)')
    s = servizio()
    ok('new_assembly', 'Impianto di scarico')
    ids = {}
    for k, nome in (('telaio', 'Telaio'), ('tramoggia', 'Tramoggia'), ('bocca', 'Bocca'), ('tronchetto', 'Tronchetto'),
                    ('cassa_cabina', 'Cabina'), ('porta_cabina', 'Porta cabina'), ('mensola', 'Mensola'),
                    ('cappa', 'Cappa'), ('camino', 'Camino'), ('deflettore', 'Deflettore')):
        if k not in F:
            BUCHI.append((f'assieme: {nome}', 'il pezzo non è stato creato, lo salto'))
            continue
        if prova(f'inserisci {nome}', ok, 'asm_insert', str(F[k])):
            iid = s.asm.instances[-1]['id']
            prova(f'nome {nome}', ok, 'asm_set', iid, {'name': nome})
            ids[nome] = iid
    if 'Telaio' in ids:
        prova('telaio fermo', ok, 'asm_set', ids['Telaio'], {'fixed': True})

    def monta():
        manca = [n for n in ('Telaio', 'Tramoggia', 'Bocca', 'Tronchetto', 'Mensola', 'Cabina', 'Porta cabina', 'Cappa', 'Camino', 'Deflettore') if n not in ids]
        for n in manca:
            ids[n] = None
        tb = bb_ist(ids['Telaio'])
        passo('tramoggia appoggiata sopra il telaio')
        tr = bb_ist(ids['Tramoggia'])
        metti(ids['Tramoggia'], centro=[tb.center().X, tb.center().Y, tb.max.Z + tr.size.Z / 2])
        trb = bb_ist(ids['Tramoggia'])
        passo('bocca sotto lo scarico (spostato di 120): girata di 180° perché il quadro stia in alto')
        bo = ids['Bocca']
        metti(bo, rot=[('x', 180)], centro=[trb.center().X + 120, trb.center().Y, trb.min.Z - bb_ist(bo).size.Z / 2])
        bob = bb_ist(bo)
        passo('tronchetto sotto la bocca, inclinato di 25° (Ruota sull’asse Y)')
        metti(ids['Tronchetto'], rot=[('y', 25)], centro=[bob.center().X + 40, bob.center().Y, bob.min.Z - 100])
        passo('mensola sulla gamba del telaio, cabina sopra la mensola, porta davanti alla cabina')
        metti(ids['Mensola'], minimo=[tb.max.X, tb.min.Y + 200, 700])
        mb = bb_ist(ids['Mensola'])
        metti(ids['Cabina'], rot=[('x', 90)], minimo=[mb.min.X + 20, mb.min.Y, mb.max.Z])
        cb = bb_ist(ids['Cabina'])
        metti(ids['Porta cabina'], rot=[('x', 90)], minimo=[cb.min.X, cb.min.Y - 25, cb.min.Z])
        passo('cappa vicino all’impianto, appesa a 2,4 m; camino sopra; deflettore sotto la cappa')
        metti(ids['Cappa'], minimo=[tb.min.X - 1100, tb.min.Y, 2400])
        kb = bb_ist(ids['Cappa'])
        metti(ids['Camino'], centro=[kb.center().X, kb.center().Y + 70, kb.max.Z + 150])
        metti(ids['Deflettore'], minimo=[kb.min.X + 50, kb.min.Y - 100, kb.min.Z - 250])
        mostra(nuovo=True)

    prova('montaggio', monta)

    def accoppia():
        passo('accoppiamento faccia su faccia: la cabina appoggiata sulla mensola')
        fc = next(f['index'] for o in s.scene()['objects'] if o['id'] == ids['Cabina'] for f in o['faces']
                  if s._asm_face(ids['Cabina'], f['index'])['kind'] == 'piana')
        fm = next(f['index'] for o in s.scene()['objects'] if o['id'] == ids['Mensola'] for f in o['faces']
                  if s._asm_face(ids['Mensola'], f['index'])['kind'] == 'piana')
        ok('asm_add_mate', 'faccia', {'inst': ids['Mensola'], 'face': fm}, {'inst': ids['Cabina'], 'face': fc}, 0, False)

    prova('accoppiamento cabina-mensola', accoppia)
    return ids


def controlli():
    titolo('9. CONTROLLI: interferenze, distinta, tavole, STEP, prepara per il laser')
    t = time.time()
    inter = ok('asm_interferences').get('interferences', [])
    passo(f'interferenze in {time.time() - t:.1f} s: ' + ('nessuna' if not inter else '; '.join(x['label'] for x in inter[:6])))
    righe = A.bom(s.asm, s.asm_parts)
    print('   DISTINTA')
    tot = 0
    for k, r in enumerate(righe, 1):
        print(f'   {k:2d}  {r["name"]:<22} {r["qty"]:>2} ×  {r["material"]:<6} sp. {r["thickness"] or "":<4} {r["mass_tot"]:8.2f} kg')
        tot += r['mass_tot']
    print(f'       {"totale":<22}{"":>27}{tot:8.2f} kg')
    ok('save', str(D / 'impianto.steelcad-asm'))
    campi = {'azienda': 'Prova SteelCAD', 'disegnatore': 'SteelCAD', 'numero': 'IM-2010', 'revisione': 'A',
             'note': 'Vetrina: impianto di scarico', 'formato': 'A3'}
    t = time.time()
    r = prova('tavole', ok, 'export_drawings', str(D / 'impianto_tavole.pdf'), campi, True)
    if r:
        passo(f'{r["message"]} ({time.time() - t:.0f} s)')
    prova('STEP assieme', ok, 'export_step', str(D / 'impianto.step'))         # Esporta → STEP, anche per l'assieme
    return inter, tot


def prepara_laser():
    global s
    titolo('10. PREPARA PER IL LASER: la cassa della cabina, dal pulsante in alto')
    s = servizio()
    if 'cassa_cabina' not in F:
        return
    ok('open', str(F['cassa_cabina']))                 # File → Apri
    info = ok('prepara_info')
    scelte = [v['id'] for v in info.get('voci', info.get('items', [])) if v.get('ok', True)] or ['laser']
    r = ok('prepara', str(D / 'laser_cabina'), scelte, {})
    passo(r.get('message') or 'pronto per il laser')


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
                self.manda({'type': 'toast', 'text': 'Diretta SteelCAD: impianto con tramoggia, bocca inclinata, cabina e cappa'})
                time.sleep(2)
        DIRETTA = Diretta(5153)
        DIRETTA.apri()
    for nome, fn in (('telaio', telaio), ('tramoggia', tramoggia), ('bocca e tronchetto', bocca), ('cabina', cabina),
                     ('mensola', mensola), ('cappa e camino', cappa), ('deflettore', deflettore)):
        prova(nome, fn)
    prova('assieme', assieme)
    esito = prova('controlli', controlli) or ([], 0)
    prova('prepara per il laser', prepara_laser)
    print(f'\nFatto in {time.time() - T0:.0f} s. File in {D}')
    print(f'COMANDI USATI ({len(USATI)}): ' + ', '.join(f'{k}×{v}' for k, v in sorted(USATI.items())))
    print(f'COMANDI NASCOSTI USATI: {len(NASCOSTI)}')
    for n, m in NASCOSTI:
        print(f' - {n}: {m}')
    lenti = sorted(((n, t) for n, t in TEMPI if t > LENTO), key=lambda x: -x[1])
    if lenti:
        print('PASSI LENTI (> 3 s):')
        for n, t in lenti[:15]:
            print(f'   {t:6.1f} s  {n}')
    print(f'BUCHI TROVATI: {len(BUCHI)}')
    for n, m in BUCHI:
        print(f' - {n}: {m}')
    if DIRETTA:
        mostra(key='0')
        DIRETTA.manda({'type': 'toast', 'text': f'Fatto in {time.time() - T0:.0f} s: {len(F)} pezzi, {esito[1]:.0f} kg, '
                       f'{len(BUCHI)} problemi, {len(NASCOSTI)} comandi nascosti', 'kind': 'err' if BUCHI or NASCOSTI else ''})
        print('La pagina resta viva: chiudi questa finestra (Ctrl+C) quando hai finito di guardare.', flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
