"""Collaudo di TUTTE le funzioni del servizio (quelle che l'interfaccia chiama), a caccia di bug.

    python tools/collaudo.py [cartella_rapporto]

Ogni chiamata si controlla così:
  BUG       eccezione non gestita, "Errore interno", oppure un'operazione rifiutata che lascia il progetto cambiato,
            oppure Annulla/Ripeti che non tornano allo stato giusto, oppure Salva → Apri che cambia il pezzo;
  SOSPETTO  un valore assurdo accettato (lunghezza negativa, raggio zero…), o un'operazione valida rifiutata;
  LENTO     più di 5 s.
Le impostazioni dell'utente non si toccano: regole di piega e recenti vanno in una cartella temporanea.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

TMP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='collaudo_'))
TMP.mkdir(parents=True, exist_ok=True)
os.environ['STEELCAD_HOME'] = str(TMP / 'home')
os.environ['STEELCAD_RULES'] = str(TMP / 'regole.json')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build123d as bd  # noqa: E402

from app.service import Service  # noqa: E402

RISULTATI: list[dict] = []
GRUPPO = ['']
N = {'chiamate': 0}
LETTURA = {'state', 'scene', 'select', 'sketch_view', 'sheet_rules', 'home_info', 'profile_suggestions', 'drawing_fields',
           'drawing_preview', 'asm_interferences', 'sketch_offset_preview', 'sketch_trim_preview',
           'sketch_extend_preview', 'import_dxf', 'import_dxf_giro', 'autosave', 'export_step', 'export_dxf',
           'export_bend_table', 'export_drawings', 'save', 'save_thumbnail', 'forget_recent'}


def annota(tipo, cosa, dettaglio=''):
    RISULTATI.append({'tipo': tipo, 'gruppo': GRUPPO[0], 'cosa': cosa, 'dettaglio': str(dettaglio)[:600]})
    if tipo != 'OK':
        print(f'  {tipo:9} {cosa}  →  {str(dettaglio)[:220]}', flush=True)


def firma(s: Service):
    """Lo stato del progetto in breve: albero, errori, volume e sviluppo del pezzo (o le pose dell'assieme)."""
    st = s.state()

    def etichette(n):
        return [n.get('label')] + [x for c in n.get('children', []) for x in etichette(c)]
    out = [tuple(etichette(st['tree'])), len(st.get('errors') or []), json.dumps(st.get('parameters'), sort_keys=True, default=str)]
    if s.asm is not None:
        out.append(tuple((i['id'], tuple(round(x, 4) for x in sum(i['R'], [])), tuple(round(x, 4) for x in i['T']))
                         for i in s.asm.instances))
        out.append(len(s.asm.mates))
    else:
        b = s.result.body if s.result is not None else None
        if b is not None:
            try:
                out.append(round(bd.Shape.cast(b.shape).volume, 2))
            except Exception:  # noqa: BLE001
                out.append('volume?')
            sh = getattr(b, 'sheet', None)
            out.append(round(sh.flat_area, 2) if sh is not None and sh.flat is not None else None)
        out.append(len(s.doc.features))
    return tuple(out)


def chiama(s: Service, nome: str, *a, atteso='ok', nota='', undo=True):
    """Chiama una funzione e controlla tutto. atteso: 'ok' | 'no' (deve rifiutare) | 'any'."""
    N['chiamate'] += 1
    cosa = f'{nome}{_corto(a)}' + (f' [{nota}]' if nota else '')
    prima = firma(s) if nome not in LETTURA else None
    t0 = time.time()
    try:
        r = getattr(s, nome)(*a)
    except Exception as ex:  # noqa: BLE001
        annota('BUG', cosa, 'eccezione non gestita: ' + ''.join(traceback.format_exception_only(type(ex), ex)).strip()
               + ' @ ' + traceback.format_exc().strip().splitlines()[-3])
        return None
    dt = time.time() - t0
    if dt > 5:
        annota('LENTO', cosa, f'{dt:.1f} s')
    if not isinstance(r, dict):
        if nome != 'profile_suggestions':
            annota('BUG', cosa, f'risposta non è un dizionario: {type(r).__name__}')
        return r
    msg = r.get('message') or ''
    if not r.get('ok') and 'Errore interno' in msg:
        annota('BUG', cosa, msg)
        return r
    if r.get('ok') is False and not msg and not r.get('cancelled'):
        annota('SOSPETTO', cosa, 'rifiutata senza messaggio')
    try:
        dopo = firma(s) if prima is not None else None
    except Exception as ex:  # noqa: BLE001
        annota('BUG', cosa, f'dopo la chiamata lo stato non si legge: {ex!r}')
        return r
    if prima is not None and not r.get('ok') and dopo != prima:
        annota('BUG', cosa, f'rifiutata ({msg[:120]}) ma il progetto è cambiato')
    if atteso == 'ok' and not r.get('ok'):
        annota('SOSPETTO', cosa, 'operazione valida rifiutata: ' + msg)
    elif atteso == 'no' and r.get('ok'):
        st = s.state()
        segnalato = (dopo is not None and prima is not None and dopo[1] > prima[1]) or             (nome in ('new_project', 'open') and st.get('errors')) or st.get('warnings')
        if segnalato:
            annota('OK', cosa, 'accettato ma segnalato come errore nel progetto')
        else:
            annota('SOSPETTO', cosa, 'valore assurdo accettato in silenzio')
    elif atteso == 'no':
        annota('OK', cosa, msg)
    else:
        annota('OK', cosa)
    # Annulla / Ripeti: solo per le modifiche riuscite
    if undo and prima is not None and r.get('ok') and dopo != prima and nome not in ('new_project', 'new_assembly', 'open', 'import_dxf_create', 'recover_unsaved', 'asm_open_part', 'asm_back'):
        u = s.undo()
        if not u.get('ok'):
            annota('BUG', cosa, 'Annulla non riesce: ' + (u.get('message') or ''))
        else:
            f_u = firma(s)
            if f_u != prima:
                annota('BUG', cosa, 'Annulla non torna allo stato di prima: ' + _diff(prima, f_u))
            rr = s.redo()
            if not rr.get('ok'):
                annota('BUG', cosa, 'Ripeti non riesce: ' + (rr.get('message') or ''))
            elif firma(s) != dopo:
                annota('BUG', cosa, 'Ripeti non torna allo stato di dopo: ' + _diff(dopo, firma(s)))
    return r


def _corto(a):
    t = json.dumps(a, default=str, ensure_ascii=False)
    return '(' + (t[1:-1] if len(t) < 90 else t[1:86] + '…') + ')'


def _diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f'campo {i}: {str(x)[:100]} → {str(y)[:100]}'
    return f'lunghezza {len(a)} → {len(b)}'


def salva_riapri(s: Service, nome: str):
    """Salva e riapre in un servizio nuovo: il pezzo deve essere lo stesso."""
    p = TMP / (nome + ('.steelcad-asm' if s.asm is not None else '.steelcad'))
    r = s.save(str(p))
    if not r.get('ok'):
        annota('BUG', f'salva {nome}', r.get('message'))
        return
    s2 = Service()
    try:
        r2 = s2.open(str(p))
    except Exception as ex:  # noqa: BLE001
        annota('BUG', f'riapri {nome}', repr(ex))
        return
    if not r2.get('ok'):
        annota('BUG', f'riapri {nome}', r2.get('message'))
        return
    a, b = firma(s), firma(s2)
    # dopo l'apertura la storia è vuota: si confrontano albero, errori, parametri, pezzo
    if a != b:
        annota('BUG', f'salva → riapri {nome}', _diff(a, b))
    else:
        annota('OK', f'salva → riapri {nome}')


def faccia_sketch(s, sid):
    """Ingombro dei bordi (riferimenti) dello sketch."""
    v = s.sketch_view(sid)['sketch']
    xs, ys = [], []
    for ln in v['lines']:
        if ln['ref'] and not ln.get('xray'):
            xs += [ln['xa'][0], ln['xb'][0]]
            ys += [ln['xa'][1], ln['xb'][1]]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 100, 100)


def entita(s, sid, kind=None):
    v = s.sketch_view(sid)['sketch']
    out = []
    for k in ('lines', 'arcs', 'circles'):
        if kind and k != kind:
            continue
        out += [e['id'] for e in v.get(k, []) if not e['ref'] and not e.get('xray')]
    return out


def gruppo(nome):
    def dec(fn):
        GRUPPI.append((nome, fn))
        return fn
    return dec


GRUPPI = []
LAM = {'name': 'Prova', 'larghezza': 200, 'profondita': 120, 'spessore': 2, 'raggio': 2, 'k': 0.4}


def lamiera(**kw):
    s = Service()
    chiama(s, 'new_project', 'lamiera', {**LAM, **kw})
    return s


# ====================================================================================== 1. nuovi progetti
@gruppo('Nuovi progetti: tutti i modelli, valori buoni e assurdi')
def g_nuovi():
    buoni = {
        'lamiera': LAM, 'zero': {'name': 'Z'}, 'piastra': {'larghezza': 300, 'altezza': 200, 'spessore': 5, 'foro': 30},
        'telaio': {}, 'vuoto': {}, 'scaffale': {}, 'armadio': {}, 'cancello': {}, 'disegno': {},
        'cono': {}, 'tramoggia': {'spessore': 2, 'raggio': 2, 'k': 0.4},
        'tramoggia_cassone': {'raggio': 3, 'k': 0.4}, 'tramoggia_cassone_flangia': None,
    }
    buoni.pop('tramoggia_cassone_flangia')
    for k, v in buoni.items():
        s = Service()
        r = chiama(s, 'new_project', k, v)
        if r and r.get('ok'):
            salva_riapri(s, f'nuovo_{k}')
            chiama(s, 'drawing_preview', None, False, atteso='any', nota=k)
    s = Service()
    chiama(s, 'new_project', 'inesistente', {}, atteso='no')
    assurdi = [
        ('lamiera', {**LAM, 'larghezza': 0}), ('lamiera', {**LAM, 'larghezza': -100}), ('lamiera', {**LAM, 'spessore': 0}),
        ('lamiera', {**LAM, 'spessore': -2}), ('lamiera', {**LAM, 'larghezza': 'abc'}), ('lamiera', {**LAM, 'raggio': -1}),
        ('lamiera', {**LAM, 'k': 2}), ('lamiera', {**LAM, 'spessore': 500}),
        ('piastra', {'larghezza': 100, 'altezza': 100, 'spessore': 5, 'foro': 150}),
        ('piastra', {'larghezza': 100, 'altezza': 100, 'spessore': 0, 'foro': 10}),
        ('piastra', {'larghezza': 100, 'altezza': 100, 'spessore': 5, 'foro': -10}),
        ('telaio', {'L': 0}), ('telaio', {'L': -500}), ('telaio', {'profilo': 'abc'}), ('telaio', {'H': 10}),
        ('scaffale', {'ripiani': 0}), ('scaffale', {'ripiani': -2}), ('scaffale', {'ripiani': 2.5}),
        ('armadio', {'P': 0}), ('cancello', {'passo': 5000}), ('cancello', {'passo': 0}), ('cancello', {'passo': -10}),
        ('cono', {'D1': 0}), ('cono', {'D1': -100}), ('cono', {'H': 0}), ('cono', {'D1': 200, 'D2': 200}),
        ('cono', {'spessore': 300}), ('cono', {'riferimento': 'boh'}), ('cono', {'modo': 'boh'}),
                ('tramoggia', {'H': 0, 'spessore': 2, 'raggio': 2, 'k': 0.4}),
        ('tramoggia', {'ex': 5000, 'spessore': 2, 'raggio': 2, 'k': 0.4}),
    ]
    for k, v in assurdi:
        s = Service()
        chiama(s, 'new_project', k, v, atteso='no')
    # casi limite ragionevoli
    for k, v in (('cono', {'D2': 0}), ('cono', {'D1': 100, 'D2': 400}), ('scaffale', {'ripiani': 1}),
                 ('lamiera', {**LAM, 'larghezza': 0.5, 'profondita': 0.5}), ('lamiera', {**LAM, 'larghezza': 20000})):
        s = Service()
        chiama(s, 'new_project', k, v, atteso='any', nota='limite')


# ====================================================================================== 2. flange
@gruppo('Flange: lunghezze, angoli, versi, posizioni, catene, orli, modifiche')
def g_flange():
    for lung, att in (('40', 'ok'), ('0', 'no'), ('-10', 'no'), ('0.1', 'any'), ('5000', 'any'), ('abc', 'no'), ('', 'any'), ('W/4', 'ok')):
        s = lamiera()
        chiama(s, 'add_flange', 'SM1', 'L1', {'length': lung}, atteso=att, nota='lunghezza')
    for ang, att in ((90, 'ok'), (45, 'ok'), (135, 'ok'), (1, 'any'), (0, 'no'), (-30, 'no'), (170, 'any'), (175, 'no'),
                     (180, 'ok'), (181, 'no'), (360, 'no')):
        s = lamiera()
        chiama(s, 'add_flange', 'SM1', 'L1', {'length': '30', 'angle': ang}, atteso=att, nota='angolo')
    for campo, val, att in (('direction', 'down', 'ok'), ('direction', 'boh', 'no'), ('position', 'outside', 'any'),
                            ('position', 'bend', 'any'), ('position', 'boh', 'no')):
        s = lamiera()
        chiama(s, 'add_flange', 'SM1', 'L1', {'length': '30', campo: val}, atteso=att, nota=campo)
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L99', {'length': '30'}, atteso='no', nota='lato inesistente')
    chiama(s, 'add_flange', 'SM9', 'L1', {'length': '30'}, atteso='no', nota='lamiera inesistente')
    chiama(s, 'add_flange', 'SM1', None, {'length': '30'}, atteso='no', nota='né lato né madre')
    chiama(s, 'add_flange', 'SM1', None, {'length': '30'}, 'FL9', atteso='no', nota='madre inesistente')
    # scatola completa con angoli e catena profonda
    s = lamiera()
    for e in ('L1', 'L2', 'L3', 'L4'):
        chiama(s, 'add_flange', 'SM1', e, {'length': '40'})
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '40'}, atteso='no', nota='seconda flangia sullo stesso lato')
    for mode in ('over', 'under', 'open'):
        chiama(s, 'set_corner', 'SM1', 'FL1', 'FL2', mode, 0.5, nota=mode)
    chiama(s, 'set_corner', 'SM1', 'FL1', 'FL2', 'boh', 0, atteso='no')
    chiama(s, 'set_corner', 'SM1', 'FL1', 'FL3', 'over', 0, atteso='no', nota='flange non adiacenti')
    chiama(s, 'set_corner', 'SM1', 'FL1', 'FL2', 'over', -1, atteso='no', nota='fessura negativa')
    chiama(s, 'set_corner', 'SM1', 'FL1', 'FL2', 'over', 5, atteso='any', nota='fessura larga')
    madre = 'FL1'
    for i in range(5):
        r = chiama(s, 'add_flange', 'SM1', None, {'length': '15', 'direction': 'up' if i % 2 else 'down'}, madre, atteso='any', nota=f'catena {i + 1}')
        if not r or not r.get('ok'):
            break
        madre = s.doc.feature('SM1')['flanges'][-1]['id']
    for mode in ('long', 'short', 'miter', 'boh'):
        chiama(s, 'set_tip_corners', 'SM1', mode, atteso='no' if mode == 'boh' else 'any', nota=mode)
    chiama(s, 'add_flange', 'SM1', None, {'length': '8', 'angle': 180}, 'FL2', atteso='any', nota='orlo')
    chiama(s, 'add_flange', 'SM1', None, {'length': '0.5', 'angle': 180}, 'FL3', atteso='no', nota='orlo più corto del raggio')
    salva_riapri(s, 'scatola')
    # modifica e cancellazione
    chiama(s, 'edit_flange', 'SM1', 'FL2', {'length': '60'})
    chiama(s, 'edit_flange', 'SM1', 'FL2', {'angle': 120})
    chiama(s, 'edit_flange', 'SM1', 'FL2', {'length': '-5'}, atteso='no')
    chiama(s, 'edit_flange', 'SM1', 'FL2', {'angle': 0}, atteso='no')
    chiama(s, 'edit_flange', 'SM1', 'FL99', {'length': '60'}, atteso='no')
    chiama(s, 'edit_flange', 'SM1', 'FL2', {'boh': 1}, atteso='any', nota='campo sconosciuto')
    chiama(s, 'delete_flange', 'SM1', 'FL1', atteso='any', nota='madre di una catena')
    chiama(s, 'delete_flange', 'SM1', 'FL99', atteso='no')
    # fori sulla flangia
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '40'})
    chiama(s, 'add_flange_hole', 'SM1', 'FL1', 50, 20, 8)
    chiama(s, 'add_flange_hole', 'SM1', 'FL1', 50, 20, 0, atteso='no', nota='diametro 0')
    chiama(s, 'add_flange_hole', 'SM1', 'FL1', 50, 20, -8, atteso='no')
    chiama(s, 'add_flange_hole', 'SM1', 'FL1', 5000, 20, 8, atteso='no', nota='fuori dalla flangia')
    chiama(s, 'add_flange_hole', 'SM1', 'FL1', 50, 20, 100, atteso='no', nota='più grande della flangia')
    chiama(s, 'delete_flange_hole', 'SM1', 'FL1', 0)
    chiama(s, 'delete_flange_hole', 'SM1', 'FL1', 7, atteso='no')
    chiama(s, 'delete_flange_hole', 'SM1', 'FL1', -1, atteso='no')
    # linguette di fine
    for end in ('start', 'end', 'boh'):
        chiama(s, 'set_end_tab', 'SM1', 'FL1', end, True, 1, atteso='no' if end == 'boh' else 'any', nota=end)
    chiama(s, 'set_end_tab', 'SM1', 'FL1', 'start', False, 0, atteso='any')
    chiama(s, 'extend_over_tab', 'SM1', 'FL1', atteso='any')


# ====================================================================================== 3. tecnologia
@gruppo('Dati di piega, regole, predefiniti')
def g_tecno():
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '40'})
    for f, att in (({'radius': 3}, 'ok'), ({'radius': 0}, 'any'), ({'radius': -1}, 'no'), ({'k': 0.33}, 'ok'), ({'k': 0}, 'any'),
                   ({'k': 1.2}, 'no'), ({'k': -0.1}, 'no'), ({'method': 'din6935'}, 'ok'), ({'method': 'bd90', 'bd90': 3.5}, 'ok'),
                   ({'method': 'bd90', 'bd90': 50}, 'no'), ({'method': 'boh'}, 'no'), ({'thickness': 3}, 'ok'),
                   ({'thickness': 0}, 'no'), ({'thickness': 'sp*2'}, 'any'), ({'radius': 'abc'}, 'no')):
        chiama(s, 'set_sheet_tech', 'SM1', f, atteso=att, nota=str(f))
    chiama(s, 'set_sheet_tech', 'SM9', {'radius': 3}, atteso='no')
    chiama(s, 'sheet_rules', atteso='any')
    chiama(s, 'save_sheet_rule', 'SM1', 'Regola prova')
    chiama(s, 'save_sheet_rule', 'SM1', '', atteso='no', nota='nome vuoto')
    chiama(s, 'save_sheet_rule', 'SM1', 'Regola prova', atteso='any', nota='stesso nome')
    chiama(s, 'apply_sheet_rule', 'SM1', 'Regola prova', atteso='any')
    chiama(s, 'apply_sheet_rule', 'SM1', 'Non esiste', atteso='no')
    chiama(s, 'delete_sheet_rule', 'Regola prova')
    chiama(s, 'delete_sheet_rule', 'Non esiste', atteso='any')
    for v, att in (({'radius': 2, 'k': 0.4}, 'ok'), ({'radius': '', 'k': 0.4}, 'no'), ({'radius': 2}, 'no'),
                   ({'radius': -2, 'k': 0.4}, 'no'), ({'radius': 2, 'k': 5}, 'no'), ({'radius': 2, 'method': 'din6935'}, 'ok'),
                   ({'radius': 'x', 'k': 0.4}, 'no')):
        chiama(s, 'set_bend_default', v, atteso=att, nota=str(v), undo=False)
    s2 = Service()
    chiama(s2, 'new_project', 'lamiera', {'name': 'Def', 'larghezza': 100, 'profondita': 80, 'spessore': 2}, nota='usa i predefiniti')
    chiama(s2, 'add_flange', 'SM1', 'L1', {'length': '20'}, nota='flangia coi predefiniti')


# ====================================================================================== 4. sketch: disegno
@gruppo('Sketch: entità, valori degeneri')
def g_sketch_entita():
    s = lamiera()
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    casi = [
        ('sketch_add_rectangle', (sid, [10, 10], [50, 40]), 'ok'),
        ('sketch_add_rectangle', (sid, [10, 10], [10, 40]), 'no'),
        ('sketch_add_rectangle', (sid, [10, 10], [10, 10]), 'no'),
        ('sketch_add_circle', (sid, [100, 60], 10), 'ok'),
        ('sketch_add_circle', (sid, [100, 60], 0), 'no'),
        ('sketch_add_circle', (sid, [100, 60], -5), 'no'),
        ('sketch_add_circle', (sid, ['a', 60], 5), 'no'),
        ('sketch_add_slot', (sid, [130, 20], [170, 20], 5), 'ok'),
        ('sketch_add_slot', (sid, [130, 20], [130, 20], 5), 'no'),
        ('sketch_add_slot', (sid, [130, 20], [170, 20], 0), 'no'),
        ('sketch_add_polygon', (sid, [60, 90], [70, 90], 6), 'ok'),
        ('sketch_add_polygon', (sid, [60, 90], [70, 90], 2), 'no'),
        ('sketch_add_polygon', (sid, [60, 90], [70, 90], 0), 'no'),
        ('sketch_add_polygon', (sid, [60, 90], [60, 90], 6), 'no'),
        ('sketch_add_polygon', (sid, [60, 90], [70, 90], 64), 'ok'),
        ('sketch_add_arc3', (sid, [20, 80], [30, 90], [40, 80]), 'ok'),
        ('sketch_add_arc3', (sid, [20, 80], [30, 80], [40, 80]), 'no'),
        ('sketch_add_arc3', (sid, [20, 80], [20, 80], [40, 80]), 'no'),
        ('sketch_add_polyline', (sid, [[150, 80], [180, 80], [180, 110]], False), 'ok'),
        ('sketch_add_polyline', (sid, [[150, 80]], False), 'no'),
        ('sketch_add_polyline', (sid, [], False), 'no'),
        ('sketch_add_polyline', (sid, [[150, 80], [150, 80]], False), 'no'),
        ('sketch_add_polyline', (sid, [[10, 100], [20, 100], [10, 100]], True), 'any'),
        ('sketch_add_circle', ('S999', [100, 60], 10), 'no'),
        ('sketch_add_circle', (sid, [1e9, 1e9], 1), 'any'),
    ]
    for nome, a, att in casi:
        chiama(s, nome, *a, atteso=att)
    chiama(s, 'sketch_view', sid, atteso='ok')
    chiama(s, 'sketch_view', 'S999', atteso='no')
    chiama(s, 'sketch_xray', sid, True)
    chiama(s, 'sketch_xray', sid, False)
    chiama(s, 'sketch_close', sid, atteso='any')
    chiama(s, 'sketch_on_face', 'SM1/inesistente', atteso='no')
    chiama(s, 'sketch_on_face', '', atteso='no')
    chiama(s, 'sketch_on_flat', 'SM9', atteso='no')
    chiama(s, 'sketch_on_flat', None, atteso='any')


@gruppo('Sketch: modifiche (raccordo, smusso, offset, taglia, allunga, specchia, copia, sposta, serie, quote)')
def g_sketch_modifiche():
    s = lamiera()
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_rectangle', sid, [20, 20], [80, 60])
    v = s.sketch_view(sid)['sketch']
    linee = [x['id'] for x in v['lines'] if not x['ref']]
    angoli = [p['id'] for p in v['points'] if p['id'] != 'O' and any(abs(p['xy'][0] - x) < 1e-6 for x in (20, 80))
              and any(abs(p['xy'][1] - y) < 1e-6 for y in (20, 60))]
    chiama(s, 'sketch_fillet', sid, angoli[0], 5)
    chiama(s, 'sketch_fillet', sid, angoli[1], 0, atteso='no')
    chiama(s, 'sketch_fillet', sid, angoli[1], -3, atteso='no')
    chiama(s, 'sketch_fillet', sid, angoli[1], 500, atteso='no', nota='raggio più grande dei lati')
    chiama(s, 'sketch_chamfer', sid, angoli[2], 4)
    chiama(s, 'sketch_chamfer', sid, angoli[3], 500, atteso='no')
    chiama(s, 'sketch_fillet', sid, 'P999', 5, atteso='no')
    chiama(s, 'sketch_fillet', sid, 'O', 5, atteso='no', nota='origine')
    v = s.sketch_view(sid)['sketch']
    linee = [x['id'] for x in v['lines'] if not x['ref']]
    tutte = entita(s, sid)
    chiama(s, 'sketch_offset_preview', sid, tutte, 3, 'out', atteso='any')
    chiama(s, 'sketch_offset', sid, tutte, 3, 'out', atteso='any')
    chiama(s, 'sketch_offset', sid, tutte, 0, 'out', atteso='no')
    chiama(s, 'sketch_offset', sid, tutte, -3, 'out', atteso='any')
    chiama(s, 'sketch_offset', sid, tutte, 500, 'in', atteso='no', nota='offset che sparisce')
    chiama(s, 'sketch_offset', sid, tutte, 3, 'boh', atteso='no')
    chiama(s, 'sketch_offset', sid, [], 3, 'out', atteso='no')
    chiama(s, 'sketch_offset_side', sid, tutte[:1], 3, [50, 0], atteso='any')
    chiama(s, 'sketch_copy', sid, tutte, 100, 0)
    chiama(s, 'sketch_copy', sid, [], 100, 0, atteso='no')
    chiama(s, 'sketch_copy', sid, ['L999'], 100, 0, atteso='no')
    chiama(s, 'sketch_move', sid, tutte, 5, 5)
    chiama(s, 'sketch_move', sid, tutte, 'a', 5, atteso='no')
    chiama(s, 'sketch_pattern', sid, tutte, 2, 0, 2, 0, atteso='no', nota='passo 0 (copie sovrapposte)')
    chiama(s, 'sketch_pattern', sid, tutte, 0, 10, 1, 10, atteso='no', nota='0 colonne')
    chiama(s, 'sketch_pattern', sid, tutte, -2, 10, 1, 10, atteso='no')
    chiama(s, 'sketch_pattern', sid, tutte[:1], 3, 5, 1, 0, atteso='any')
    # specchia attorno a una linea di costruzione
    r = chiama(s, 'sketch_add_polyline', sid, [[100, 0], [100, 120]], False, True)
    asse = [x['id'] for x in s.sketch_view(sid)['sketch']['lines'] if x.get('construction') and not x['ref']]
    if asse:
        chiama(s, 'sketch_mirror', sid, tutte[:4], asse[-1])
    chiama(s, 'sketch_mirror', sid, tutte[:4], 'L999', atteso='no')
    chiama(s, 'sketch_mirror', sid, tutte[:4], tutte[0], atteso='any', nota='asse dentro la selezione')
    chiama(s, 'sketch_construction', sid, tutte[:2], True)
    chiama(s, 'sketch_construction', sid, tutte[:2], False)
    chiama(s, 'sketch_construction', sid, ['L1'], True, atteso='no', nota='bordo del pezzo')
    # quote
    v = s.sketch_view(sid)['sketch']
    lin = [x['id'] for x in v['lines'] if not x['ref'] and not x.get('construction')]
    for kind, refs, att in (('length', lin[:1], 'any'), ('distance', lin[:2], 'any'), ('angle', lin[:2], 'any'),
                            ('boh', lin[:1], 'no'), ('length', ['L999'], 'no'), ('length', [], 'no')):
        chiama(s, 'sketch_dimension', sid, kind, refs, atteso=att, nota=kind)
    sk = s.doc.sketch(sid)
    from cad_engine.sketch.model import DIMENSIONS
    dims = [k for k, c in sk.constraints.items() if c['type'] in DIMENSIONS]
    if dims:
        d = dims[0]
        for val, att in ((55, 'any'), (0, 'no'), (-10, 'no'), ('W/4', 'any'), ('pippo*2', 'no'), ('', 'no'), ('1/0', 'no')):
            chiama(s, 'set_dimension', sid, d, val, atteso=att, nota=f'quota {val}')
    chiama(s, 'set_dimension', sid, 'D999', 10, atteso='no')
    # taglia / allunga
    s = lamiera()
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[10, 50], [190, 50]], False)
    chiama(s, 'sketch_add_polyline', sid, [[100, 10], [100, 110]], False)
    ln = entita(s, sid, 'lines')
    chiama(s, 'sketch_trim_preview', sid, ln[0], [150, 50], atteso='any')
    chiama(s, 'sketch_trim', sid, ln[0], [150, 50], atteso='any')
    chiama(s, 'sketch_trim', sid, 'L999', [150, 50], atteso='no')
    chiama(s, 'sketch_trim', sid, ln[-1], [5000, 5000], atteso='any', nota='clic lontano')
    chiama(s, 'sketch_add_polyline', sid, [[10, 90], [60, 90]], False)
    ln = entita(s, sid, 'lines')
    chiama(s, 'sketch_extend_preview', sid, ln[-1], [55, 90], atteso='any')
    chiama(s, 'sketch_extend', sid, ln[-1], [55, 90], atteso='any')
    chiama(s, 'sketch_extend', sid, 'L999', [55, 90], atteso='no')
    chiama(s, 'sketch_delete', sid, ln[:1])
    chiama(s, 'sketch_delete', sid, ['L1'], atteso='no', nota='bordo del pezzo')
    chiama(s, 'sketch_delete', sid, [], atteso='any')
    chiama(s, 'sketch_delete', sid, ['X999'], atteso='no')
    # raccordo/smusso tra due linee
    chiama(s, 'sketch_add_polyline', sid, [[120, 20], [180, 20], [180, 100]], False)
    ln = entita(s, sid, 'lines')
    chiama(s, 'sketch_fillet_lines', sid, ln[-2], ln[-1], [150, 20], [180, 60], 8, atteso='any')
    chiama(s, 'sketch_chamfer_lines', sid, ln[-2], ln[-1], [150, 20], [180, 60], -2, atteso='no')


@gruppo('Sketch → feature: tagli, aggiunte, forme, fori speciali, sullo sviluppo')
def g_sketch_feature():
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '40'})
    chiama(s, 'add_flange', 'SM1', 'L2', {'length': '40'})
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'create_from_sketch', sid, 'cut', {}, atteso='no', nota='sketch vuoto')
    chiama(s, 'sketch_add_circle', sid, [60, 60], 8)
    chiama(s, 'create_from_sketch', sid, 'boh', {}, atteso='no')
    chiama(s, 'create_from_sketch', sid, 'cut', {})
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_circle', sid, [5000, 60], 8)
    chiama(s, 'create_from_sketch', sid, 'cut', {}, atteso='no', nota='fuori dal pezzo')
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[30, 30], [60, 30], [60, 50]], False)
    chiama(s, 'create_from_sketch', sid, 'cut', {}, atteso='no', nota='contorno aperto in mezzo')
    # tipi di foro
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_circle', sid, [100, 80], 2.75)
    cid = entita(s, sid, 'circles')
    for spec, att in (({'tipo': 'svasato', 'D': 9, 'angolo': 90}, 'ok'), ({'tipo': 'svasato', 'D': 3, 'angolo': 90}, 'no'),
                      ({'tipo': 'filettato', 'M': 'M5'}, 'ok'), ({'tipo': 'filettato', 'M': 'M99'}, 'no'),
                      ({'tipo': 'boh'}, 'no'), (None, 'ok')):
        chiama(s, 'sketch_hole_type', sid, cid, spec, atteso=att, nota=str(spec))
    chiama(s, 'sketch_hole_type', sid, ['L1'], {'tipo': 'filettato', 'M': 'M5'}, atteso='no', nota='non un cerchio')
    chiama(s, 'sketch_hole_type', sid, cid, {'tipo': 'filettato', 'M': 'M5'})
    chiama(s, 'create_from_sketch', sid, 'cut', {})
    # persiane e imbutiture
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[120, 30], [170, 30]], False)
    chiama(s, 'create_from_sketch', sid, 'louver', {'width': 6, 'height': 3})
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[120, 60], [170, 60]], False)
    chiama(s, 'create_from_sketch', sid, 'louver', {'width': 0, 'height': 3}, atteso='no')
    chiama(s, 'create_from_sketch', sid, 'louver', {'width': 6, 'height': 50}, atteso='no', nota='più alta che larga')
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_circle', sid, [40, 100], 10)
    chiama(s, 'create_from_sketch', sid, 'dimple', {'depth': 3})
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_circle', sid, [160, 100], 10)
    chiama(s, 'create_from_sketch', sid, 'dimple', {'depth': 0}, atteso='no')
    chiama(s, 'create_from_sketch', sid, 'dimple', {'depth': -3}, atteso='any')
    chiama(s, 'create_from_sketch', sid, 'dimple', {'depth': 500}, atteso='no')
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_circle', sid, [40, 100], 12)
    chiama(s, 'create_from_sketch', sid, 'dimple', {'depth': 3}, atteso='no', nota='sopra un’altra imbutitura')
    # estrusione (boss) e aggiunta materiale
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_rectangle', sid, [140, 85], [160, 105])
    chiama(s, 'create_from_sketch', sid, 'boss', {'height': 10}, atteso='any')
    sid = chiama(s, 'sketch_on_face', 'SM1/FL1/esterno')['sketch']
    x0, y0, x1, y1 = faccia_sketch(s, sid)
    chiama(s, 'sketch_add_polyline', sid, [[x0 + 30, y1], [x0 + 30, y1 + 15], [x0 + 60, y1 + 15], [x0 + 60, y1]], False)
    chiama(s, 'sheet_tab', sid, atteso='any')
    sid = chiama(s, 'sketch_on_face', 'SM1/FL1/esterno')['sketch']
    chiama(s, 'sheet_tab', sid, atteso='no', nota='sketch vuoto')
    # sullo sviluppo: taglio che passa la piega
    sid = chiama(s, 'sketch_on_flat', 'SM1')['sketch']
    chiama(s, 'sketch_add_slot', sid, [100, -20], [100, 15], 4)
    chiama(s, 'create_from_sketch', sid, 'cut', {})
    salva_riapri(s, 'feature_varie')
    # piega su linea
    s = lamiera()
    sid = chiama(s, 'sketch_on_flat', 'SM1')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[-5, 40], [205, 40]], False)
    chiama(s, 'sheet_fold', sid, 90, 'up', False)
    fo = [f['id'] for f in s.doc.feature('SM1').get('folds') or []]
    if fo:
        chiama(s, 'edit_fold', 'SM1', fo[0], {'angle': 45})
        chiama(s, 'edit_fold', 'SM1', fo[0], {'angle': 0}, atteso='no')
        chiama(s, 'edit_fold', 'SM1', fo[0], {'angle': 200}, atteso='no')
        chiama(s, 'edit_fold', 'SM1', fo[0], {'direction': 'down'})
        chiama(s, 'add_flange', 'SM1', None, {'length': '10'}, fo[0], atteso='any', nota='flangia sulla punta della piega')
        salva_riapri(s, 'piega_su_linea')
        chiama(s, 'delete_fold', 'SM1', fo[0], atteso='any')
    chiama(s, 'delete_fold', 'SM1', 'PL99', atteso='no')
    sid = chiama(s, 'sketch_on_flat', 'SM1')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[50, 40], [150, 40]], False)
    chiama(s, 'sheet_fold', sid, 90, 'up', False, atteso='no', nota='linea che non attraversa')
    sid = chiama(s, 'sketch_on_flat', 'SM1')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[-5, 60], [205, 60]], False)
    chiama(s, 'sheet_fold', sid, 0, 'up', False, atteso='no', nota='angolo 0')
    chiama(s, 'sheet_fold', sid, 90, 'boh', False, atteso='no')
    # lamiera a contorno
    s = lamiera()
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'sketch_add_polyline', sid, [[0, 0], [0, -30], [60, -30]], False)
    chiama(s, 'contour_flange', sid, atteso='any')
    sid = chiama(s, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(s, 'contour_flange', sid, atteso='no', nota='vuoto')
    # incastri automatici
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '40'})
    chiama(s, 'add_flange', 'SM1', None, {'length': '30'}, 'FL1')
    chiama(s, 'add_flange', 'SM1', None, {'length': '38'}, 'FL2')
    for n, w, g, att in ((3, 15, 0.2, 'any'), (0, 15, 0.2, 'no'), (3, 0, 0.2, 'no'), (3, 15, -1, 'no'), (100, 15, 0.2, 'no'),
                         (3, 500, 0.2, 'no')):
        chiama(s, 'auto_tabs', 'SM1', 'FL3', n, w, g, 0, atteso=att, nota=f'n={n} w={w} g={g}')
    chiama(s, 'auto_tabs', 'SM1', 'FL1', 3, 15, 0.2, 0, atteso='no', nota='flangia che non tocca la base')


# ====================================================================================== 5. parametri
@gruppo('Parametri e misure')
def g_parametri():
    s = lamiera()
    for nome, val, att in (('W', 250, 'ok'), ('W', 0, 'no'), ('W', -10, 'no'), ('W', 'abc', 'no'), ('W', 'P*2', 'ok'),
                           ('nuovo', 33, 'ok'), ('2abc', 5, 'no'), ('a b', 5, 'no'), ('', 5, 'no'), ('x', 'x+1', 'no'),
                           ('y', 'z+1', 'no'), ('sp', 0, 'no'), ('sp', 1e6, 'no'), ('W', '1/0', 'no'), ('W', 'sqrt(-1)', 'no')):
        chiama(s, 'set_parameter', nome, val, atteso=att, nota=f'{nome}={val}')
    s = lamiera()
    chiama(s, 'set_parameter', 'a', 10)
    chiama(s, 'set_parameter', 'b', 'a*2')
    chiama(s, 'set_parameter', 'a', 'b', atteso='no', nota='circolare')


# ====================================================================================== 6. strutture
@gruppo('Strutture: aste, giunti, nodi, modelli')
def g_strutture():
    s = Service()
    chiama(s, 'new_project', 'telaio', {})
    chiama(s, 'profile_suggestions', atteso='any')
    sc = s.scene()
    asta = sc['objects'][0]['id']
    st = asta.split('/')[0]
    chiama(s, 'select', asta, atteso='any')
    chiama(s, 'select', 'ST1/M999', atteso='no')
    chiama(s, 'select', '', atteso='any')
    for f, att in (({'profile': '50x50x3'}, 'ok'), ({'profile': 'abc'}, 'no'), ({'profile': ''}, 'no'),
                   ({'profile': 'IPE200'}, 'any'), ({'profile': 'tondo 30'}, 'any'), ({'rotate_by': 90}, 'ok'),
                   ({'toggle_flip': True}, 'ok'), ({'anchor': 'top'}, 'ok'), ({'anchor': 'boh'}, 'no')):
        chiama(s, 'edit_member', asta, f, False, atteso=att, nota=str(f))
    chiama(s, 'edit_member', asta, {'profile': '30x30x2'}, True, nota='tutto il gruppo')
    chiama(s, 'edit_member', 'ST1/M999', {'profile': '30x30x2'}, False, atteso='no')
    nodi = sc['nodes']
    k = nodi[0]['key']
    for spec, att in (({'type': 'miter'}, 'any'), ({'type': 'butt', 'through': nodi[0]['members'][:1]}, 'any'),
                      ({'type': 'butt'}, 'no'), ({'type': 'butt', 'through': nodi[0]['members']}, 'no'),
                      ({'type': 'extend'}, 'any'), ({'type': 'boh'}, 'no'), ({'type': 'auto'}, 'ok')):
        chiama(s, 'set_joint', st, k, spec, atteso=att, nota=str(spec))
    chiama(s, 'set_joint', st, 'T999', {'type': 'auto'}, atteso='no')
    chiama(s, 'move_node', st, k, [10, 0, 0], atteso='any')
    chiama(s, 'move_node', st, k, ['a', 0, 0], atteso='no')
    chiama(s, 'move_node', st, 'T999', [10, 0, 0], atteso='no')
    chiama(s, 'add_member', st, k, None, 'Z+', 300, '40x40x3', None, atteso='any', nota='asta nuova in su')
    chiama(s, 'add_member', st, k, None, 'Z+', 0, '40x40x3', None, atteso='no', nota='lunghezza 0')
    chiama(s, 'add_member', st, k, None, 'Z+', -300, '40x40x3', None, atteso='no')
    chiama(s, 'add_member', st, k, None, 'boh', 300, '40x40x3', None, atteso='no')
    chiama(s, 'add_member', st, k, k, None, None, '40x40x3', None, atteso='no', nota='da un nodo a sé stesso')
    chiama(s, 'add_member', st, 'T999', None, 'Z+', 300, '40x40x3', None, atteso='no')
    chiama(s, 'delete_members', [asta])
    chiama(s, 'delete_members', ['ST1/M999'], atteso='no')
    chiama(s, 'delete_members', [], atteso='any')
    salva_riapri(s, 'telaio_modificato')
    # modelli: misure cambiate dopo
    for kind, vals in (('telaio', {'L': 1500}), ('scaffale', {'ripiani': 5}), ('armadio', {'H': 1500}), ('cancello', {'L': 2000})):
        s = Service()
        chiama(s, 'new_project', kind, {})
        tid = next((f['id'] for f in s.doc.features if isinstance(f, dict) and f.get('type') == 'structure'), 'ST1')
        chiama(s, 'structure_template_apply', tid, vals, nota=kind)
        chiama(s, 'structure_template_apply', tid, {k: -5 for k in vals}, atteso='no', nota=kind + ' negativo')
        chiama(s, 'structure_template_apply', tid, {k: 'abc' for k in vals}, atteso='no', nota=kind + ' testo')
        chiama(s, 'structure_template_apply', 'ST999', vals, atteso='no')
        salva_riapri(s, f'modello_{kind}')
    s = Service()
    chiama(s, 'new_project', 'tramoggia_cassone', {'raggio': 3, 'k': 0.4, 'flangia': 40, 'smusso': 60, 'divisione': 'verticali'})
    sel = s.select('body').get('selection') or {}
    forma = sel.get('forma') or {}
    for x in (forma.get('spigoli') or [])[:4]:
        chiama(s, 'set_shape_edge', sel['tpl_id'], x['key'], 'piega', atteso='any', nota=x['nome'])
        chiama(s, 'set_shape_edge', sel['tpl_id'], x['key'], 'saldatura', atteso='any', nota=x['nome'])
    chiama(s, 'set_shape_edge', sel.get('tpl_id', 'FM1'), 'lato:boh:9', 'piega', atteso='no')
    chiama(s, 'set_shape_edge', sel.get('tpl_id', 'FM1'), (forma.get('spigoli') or [{'key': 'x'}])[0]['key'], 'boh', atteso='no')
    chiama(s, 'structure_template_apply', sel.get('tpl_id', 'FM1'), {'A': 800, 'divisione': 'lati'})
    chiama(s, 'structure_template_apply', sel.get('tpl_id', 'FM1'), {'foglio': 'abc'}, atteso='no')
    salva_riapri(s, 'tramoggia_cassone')
    chiama(s, 'export_dxf', str(TMP / 'tramoggia.dxf'))
    chiama(s, 'drawing_preview', None, False, nota='tramoggia')
    for kind in ('cono', 'tramoggia'):
        s = Service()
        chiama(s, 'new_project', kind, {'spessore': 2, 'raggio': 2, 'k': 0.4} if kind == 'tramoggia' else {})
        sel = s.select('body')
        tid = (sel.get('selection') or {}).get('tpl_id')
        if tid:
            chiama(s, 'structure_template_apply', tid, {'H': 450}, atteso='any', nota=kind)
            chiama(s, 'structure_template_apply', tid, {'H': 0}, atteso='no', nota=kind + ' altezza 0')
        salva_riapri(s, f'forma_{kind}')
        chiama(s, 'drawing_preview', None, False, atteso='any', nota=kind)


# ====================================================================================== 7. struttura da disegno
@gruppo('Struttura da disegno e struttura libera')
def g_strutture_disegno():
    s = Service()
    chiama(s, 'new_project', 'disegno', {})
    sid = next((f.id for f in s.doc.features if not isinstance(f, dict)), None)
    if sid:
        chiama(s, 'sketch_add_polyline', sid, [[0, 0], [0, 1000], [800, 1000], [800, 0]], False)
        chiama(s, 'create_from_sketch', sid, 'structure', {'profile': '40x40x3'}, atteso='any')
        chiama(s, 'create_from_sketch', sid, 'structure', {'profile': 'abc'}, atteso='no')
        salva_riapri(s, 'struttura_disegno')
    s = Service()
    chiama(s, 'new_project', 'vuoto', {})
    sc = s.scene()
    nodi = sc.get('nodes') or []
    if nodi:
        st, k = nodi[0]['structure'], nodi[0]['key']
        chiama(s, 'add_member', st, k, None, 'X+', 500, '40x40x3', None)
        chiama(s, 'add_member', st, k, None, 'Z+', 500, '40x40x3', None)
    s = Service()
    chiama(s, 'new_project', 'zero', {})
    chiama(s, 'sketch_add_rectangle', 'S1', [0, 0], [200, 100])
    chiama(s, 'create_from_sketch', 'S1', 'sheet', {'thickness': 2, 'radius': 2, 'k': 0.4})
    s = Service()
    chiama(s, 'new_project', 'zero', {})
    chiama(s, 'sketch_add_rectangle', 'S1', [0, 0], [200, 100])
    chiama(s, 'create_from_sketch', 'S1', 'plate', {'thickness': 8})
    chiama(s, 'create_from_sketch', 'S1', 'plate', {'thickness': 0}, atteso='no')
    s = Service()
    chiama(s, 'new_project', 'zero', {})
    chiama(s, 'create_from_sketch', 'S1', 'sheet', {'thickness': 2, 'radius': 2, 'k': 0.4}, atteso='no', nota='sketch vuoto')
    chiama(s, 'sketch_add_rectangle', 'S1', [0, 0], [200, 100])
    chiama(s, 'create_from_sketch', 'S1', 'sheet', {'thickness': -2, 'radius': 2, 'k': 0.4}, atteso='no')


# ====================================================================================== 8. import DXF
@gruppo('Import DXF / DWG')
def g_import():
    import ezdxf
    s = Service()
    chiama(s, 'import_dxf', str(TMP / 'non_esiste.dxf'), atteso='no')
    (TMP / 'vuoto.dxf').write_text('', encoding='utf-8')
    chiama(s, 'import_dxf', str(TMP / 'vuoto.dxf'), atteso='no', nota='file vuoto')
    (TMP / 'spazzatura.dxf').write_bytes(os.urandom(2000))
    chiama(s, 'import_dxf', str(TMP / 'spazzatura.dxf'), atteso='no', nota='file a caso')
    (TMP / 'finto.dwg').write_bytes(b'AC1032' + os.urandom(500))
    chiama(s, 'import_dxf', str(TMP / 'finto.dwg'), atteso='no', nota='DWG')
    d = ezdxf.new()
    d.saveas(TMP / 'senza_niente.dxf')
    chiama(s, 'import_dxf', str(TMP / 'senza_niente.dxf'), atteso='no', nota='DXF senza geometria')
    d = ezdxf.new()
    m = d.modelspace()
    m.add_line((0, 0), (100, 0))
    m.add_line((100, 0), (100, 50))
    d.saveas(TMP / 'aperto.dxf')
    chiama(s, 'import_dxf', str(TMP / 'aperto.dxf'), atteso='no', nota='contorno aperto')
    d = ezdxf.new()
    d.layers.add('PIEGA')
    m = d.modelspace()
    m.add_lwpolyline([(0, 0), (300, 0), (300, 100), (0, 100)], close=True)
    m.add_circle((150, 50), 5)
    m.add_line((0, 20), (300, 20), dxfattribs={'layer': 'PIEGA'})
    d.saveas(TMP / 'buono.dxf')
    r = chiama(s, 'import_dxf', str(TMP / 'buono.dxf'))
    if r and r.get('ok'):
        chiama(s, 'import_dxf_giro', r['scelto'])
        chiama(s, 'import_dxf_giro', 999, atteso='no')
        chiama(s, 'import_dxf_giro', -1, atteso='no')
        chiama(s, 'import_dxf_giro', 'abc', atteso='no')
        P = {'thickness': 2, 'radius': 2, 'k': 0.4}
        for p, att in (({**P, 'thickness': ''}, 'no'), ({**P, 'radius': ''}, 'no'), ({**P, 'k': ''}, 'no'), ({**P, 'thickness': -1}, 'no'),
                       ({**P, 'angle': 0}, 'no'), ({**P, 'angle': 200}, 'no'), ({**P, 'direction': 'boh'}, 'no'),
                       ({**P, 'material': 'BOH'}, 'no'), ({**P, 'thickness': 50}, 'no'), ({**P, 'k': 3}, 'no')):
            chiama(s, 'import_dxf_create', r['scelto'], p, atteso=att, nota=str(p))
        chiama(s, 'import_dxf_create', 999, P, atteso='no')
        chiama(s, 'import_dxf_create', r['scelto'], P)
        salva_riapri(s, 'importato')
    s2 = Service()
    chiama(s2, 'import_dxf_giro', 0, atteso='no', nota='senza file')
    chiama(s2, 'import_dxf_create', 0, {'thickness': 2, 'radius': 2, 'k': 0.4}, atteso='no', nota='senza file')
    for f in sorted(Path(r'C:\Users\villa\Downloads\ufficio_tecnico_taglio_piega_DXF').glob('*.dxf'))[:13]:
        r = chiama(s2, 'import_dxf', str(f), atteso='any', nota=f.name)
        if r and r.get('ok') and r.get('scelto') is not None:
            chiama(s2, 'import_dxf_create', r['scelto'], {'thickness': 1.5, 'radius': 1.5, 'k': 0.4}, atteso='any', nota=f.name)


# ====================================================================================== 9. assiemi
@gruppo('Assiemi: inserisci, sposta, ruota, accoppiamenti, interferenze, incastri, apri e torna')
def g_assiemi():
    a = lamiera()
    chiama(a, 'add_flange', 'SM1', 'L1', {'length': '40'})
    sid = chiama(a, 'sketch_on_face', 'SM1/sopra')['sketch']
    chiama(a, 'sketch_add_circle', sid, [50, 60], 4)
    chiama(a, 'sketch_add_circle', sid, [150, 60], 4)
    chiama(a, 'create_from_sketch', sid, 'cut', {})
    chiama(a, 'save', str(TMP / 'p1.steelcad'))
    s = Service()
    chiama(s, 'new_assembly', 'Assieme prova')
    chiama(s, 'new_assembly', '', atteso='any', nota='nome vuoto')
    chiama(s, 'asm_insert', str(TMP / 'p1.steelcad'))
    chiama(s, 'asm_insert', str(TMP / 'p1.steelcad'), nota='stesso file due volte')
    chiama(s, 'asm_insert', str(TMP / 'non_esiste.steelcad'), atteso='no')
    chiama(s, 'asm_insert', str(TMP / 'buono.dxf'), atteso='no', nota='un DXF')
    ids = [i['id'] for i in s.asm.instances]
    chiama(s, 'asm_move', ids[1], 0, 0, 50)
    chiama(s, 'asm_move', ids[1], 'a', 0, 0, atteso='no')
    chiama(s, 'asm_move', 'I999', 0, 0, 5, atteso='no')
    chiama(s, 'asm_move', ids[1], float('nan'), 0, 0, atteso='no', nota='NaN')
    chiama(s, 'asm_rotate', ids[1], 'z', 90)
    chiama(s, 'asm_rotate', ids[1], 'w', 90, atteso='no')
    chiama(s, 'asm_rotate', ids[1], 'x', 'abc', atteso='no')
    chiama(s, 'asm_set', ids[1], {'name': 'Seconda'})
    chiama(s, 'asm_set', ids[1], {'name': ''}, atteso='any')
    chiama(s, 'asm_set', ids[1], {'fixed': True})
    chiama(s, 'asm_set', 'I999', {'name': 'x'}, atteso='no')
    # accoppiamenti
    def facce(iid, kind):
        out = []
        for o in s.scene()['objects']:
            if o['id'] == iid:
                for f in o['faces']:
                    inf = s._asm_face(iid, f['index'])
                    if inf['kind'] == kind:
                        out.append((f['index'], inf))
        return out
    p0 = facce(ids[0], 'piana')
    p1 = facce(ids[1], 'piana')
    c0 = facce(ids[0], 'cilindrica')
    c1 = facce(ids[1], 'cilindrica')
    sopra0 = next(i for i, inf in p0 if inf['name'] == 'SM1/sopra')
    sotto1 = next(i for i, inf in p1 if inf['name'] == 'SM1/sotto')
    chiama(s, 'asm_add_mate', 'faccia', {'inst': ids[0], 'face': sopra0}, {'inst': ids[1], 'face': sotto1}, 0, False)
    if c0 and c1:
        chiama(s, 'asm_add_mate', 'asse', {'inst': ids[0], 'face': c0[0][0]}, {'inst': ids[1], 'face': c1[0][0]}, 0, False)
        chiama(s, 'asm_add_mate', 'asse', {'inst': ids[0], 'face': c0[0][0]}, {'inst': ids[1], 'face': sotto1}, 0, False,
               atteso='no', nota='asse con una faccia piana')
    chiama(s, 'asm_add_mate', 'boh', {'inst': ids[0], 'face': sopra0}, {'inst': ids[1], 'face': sotto1}, atteso='no')
    chiama(s, 'asm_add_mate', 'faccia', {'inst': ids[0], 'face': sopra0}, {'inst': ids[0], 'face': sopra0}, atteso='no', nota='stesso pezzo')
    chiama(s, 'asm_add_mate', 'faccia', {'inst': ids[0], 'face': 99999}, {'inst': ids[1], 'face': sotto1}, atteso='no')
    chiama(s, 'asm_add_mate', 'faccia', {'inst': 'I999', 'face': 0}, {'inst': ids[1], 'face': sotto1}, atteso='no')
    chiama(s, 'asm_add_mate', 'faccia', {'inst': ids[0], 'face': sopra0}, {'inst': ids[1], 'face': sotto1}, 'abc', atteso='no')
    mates = [m['id'] for m in s.asm.mates]
    if mates:
        chiama(s, 'asm_edit_mate', mates[0], {'offset': 5})
        chiama(s, 'asm_edit_mate', mates[0], {'flip': True}, atteso='any')
        chiama(s, 'asm_edit_mate', mates[0], {'offset': 'abc'}, atteso='no')
        chiama(s, 'asm_edit_mate', mates[0], {'off': True}, atteso='any', nota='spento')
        chiama(s, 'asm_edit_mate', 'M999', {'offset': 5}, atteso='no')
    chiama(s, 'asm_interferences', atteso='any')
    chiama(s, 'asm_tabs', ids[1], sotto1, 2, 10, 0.2, 0, atteso='any')
    chiama(s, 'asm_tabs', ids[1], sotto1, 0, 10, 0.2, 0, atteso='no')
    chiama(s, 'asm_tabs', 'I999', 0, 2, 10, 0.2, 0, atteso='no')
    chiama(s, 'drawing_preview', None, True, atteso='any', nota='assieme con le tavole dei pezzi')
    chiama(s, 'asm_export_step', str(TMP / 'asm.step'), atteso='any')
    salva_riapri(s, 'assieme')
    r = chiama(s, 'asm_open_part', ids[0])
    chiama(s, 'set_parameter', 'W', 260, nota='modifica il pezzo aperto dall’assieme')
    chiama(s, 'asm_back', atteso='no', nota='pezzo modificato e non salvato')
    chiama(s, 'save', None, nota='salva il pezzo aperto dall’assieme')
    chiama(s, 'asm_back')
    chiama(s, 'asm_interferences', nota='dopo il ritorno')
    chiama(s, 'asm_open_part', 'I999', atteso='no')
    if mates:
        chiama(s, 'asm_delete_mate', mates[0])
    chiama(s, 'asm_delete_mate', 'M999', atteso='no')
    chiama(s, 'asm_remove', ids[1])
    chiama(s, 'asm_remove', 'I999', atteso='no')
    chiama(s, 'asm_back', atteso='no', nota='non c’è un assieme da cui tornare')
    # comandi dell'assieme mentre si lavora su un pezzo
    p = lamiera()
    for nome, a_ in (('asm_interferences', ()), ('asm_move', ('I1', 1, 0, 0)), ('asm_insert', (str(TMP / 'p1.steelcad'),)),
                     ('asm_export_step', (str(TMP / 'x.step'),)), ('asm_remove', ('I1',)), ('asm_back', ())):
        chiama(p, nome, *a_, atteso='no', nota='fuori da un assieme')
    # assieme vuoto
    s = Service()
    chiama(s, 'new_assembly', 'Vuoto')
    chiama(s, 'asm_interferences', atteso='any')
    chiama(s, 'drawing_preview', None, False, atteso='no', nota='assieme vuoto')
    chiama(s, 'save', str(TMP / 'vuoto.steelcad-asm'), atteso='any')
    # il pezzo cambia sul disco: l'assieme si riapre lo stesso
    a = lamiera()
    chiama(a, 'save', str(TMP / 'p2.steelcad'))
    s = Service()
    chiama(s, 'new_assembly', 'Con pezzo sparito')
    chiama(s, 'asm_insert', str(TMP / 'p2.steelcad'))
    chiama(s, 'save', str(TMP / 'sparito.steelcad-asm'))
    (TMP / 'p2.steelcad').unlink()
    s2 = Service()
    chiama(s2, 'open', str(TMP / 'sparito.steelcad-asm'), atteso='any', nota='pezzo cancellato dal disco')
    try:
        s2.state()
        s2.scene()
    except Exception as ex:  # noqa: BLE001
        annota('BUG', 'assieme con pezzo mancante', repr(ex))


# ====================================================================================== 10. file
@gruppo('File: salva, apri, recupero, recenti, miniature, esportazioni')
def g_file():
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '30'})
    chiama(s, 'save', str(TMP / 'cartella_che_non_esiste' / 'x.steelcad'), atteso='any', nota='cartella inesistente')
    chiama(s, 'save', str(TMP / 'senza_estensione'), atteso='any')
    chiama(s, 'save', '', atteso='no')
    chiama(s, 'save', None, atteso='any', nota='mai salvato')
    chiama(s, 'save', str(TMP / 'normale.steelcad'))
    chiama(s, 'save', None, nota='risalva sullo stesso file')
    chiama(s, 'autosave', atteso='any')
    chiama(s, 'export_step', str(TMP / 'p.step'))
    chiama(s, 'export_dxf', str(TMP / 'p.dxf'))
    chiama(s, 'export_bend_table', str(TMP / 'p.csv'), atteso='any')
    chiama(s, 'export_step', str(TMP / 'cartella_che_non_esiste' / 'p.step'), atteso='no')
    s2 = Service()
    chiama(s2, 'open', str(TMP / 'non_esiste.steelcad'), atteso='no')
    (TMP / 'rotto.steelcad').write_text('{questo non è json', encoding='utf-8')
    chiama(s2, 'open', str(TMP / 'rotto.steelcad'), atteso='no', nota='file rotto')
    (TMP / 'vuoto.steelcad').write_text('', encoding='utf-8')
    chiama(s2, 'open', str(TMP / 'vuoto.steelcad'), atteso='no', nota='file vuoto')
    (TMP / 'strano.steelcad').write_text(json.dumps({'format': 'steelcad', 'version': 999, 'features': 'boh'}), encoding='utf-8')
    chiama(s2, 'open', str(TMP / 'strano.steelcad'), atteso='no', nota='versione futura')
    (TMP / 'altro.steelcad').write_text(json.dumps([1, 2, 3]), encoding='utf-8')
    chiama(s2, 'open', str(TMP / 'altro.steelcad'), atteso='no', nota='JSON che non è un progetto')
    # un progetto con una feature che non si costruisce più: si apre lo stesso e lo dice
    doc = json.loads((TMP / 'normale.steelcad').read_text(encoding='utf-8'))
    try:
        for f in doc.get('features', []):
            if f.get('type') == 'sheet':
                f['flanges'][0]['length'] = -50
        (TMP / 'feature_rotta.steelcad').write_text(json.dumps(doc), encoding='utf-8')
        r = chiama(s2, 'open', str(TMP / 'feature_rotta.steelcad'), atteso='any', nota='flangia rotta nel file')
        if r and r.get('ok') and not s2.state()['errors']:
            annota('SOSPETTO', 'flangia rotta nel file', 'aperto senza segnalare errori')
    except Exception as ex:  # noqa: BLE001
        annota('BUG', 'file con feature rotta', repr(ex))
    chiama(s2, 'home_info', atteso='any')
    chiama(s2, 'forget_recent', str(TMP / 'normale.steelcad'), atteso='any')
    chiama(s2, 'forget_recent', 'Z:/niente', atteso='any')
    chiama(s2, 'recover_unsaved', atteso='any')
    chiama(s2, 'save_thumbnail', str(TMP / 'normale.steelcad'), 'data:image/png;base64,iVBORw0KGgo=', atteso='any')
    chiama(s2, 'save_thumbnail', str(TMP / 'normale.steelcad'), 'spazzatura', atteso='any')
    chiama(s2, 'save_thumbnail', str(TMP / 'non_esiste.steelcad'), 'data:image/png;base64,AAAA', atteso='any')


# ====================================================================================== 11. tavole
@gruppo('Tavole: anteprima ed esportazione per ogni tipo di progetto')
def g_tavole():
    campi_strani = {'azienda': 'Ditta "con" <virgolette> & accenti èàù ' + 'X' * 300, 'disegnatore': '',
                    'numero': '../../etc', 'revisione': 'Z', 'note': 'riga\nnuova', 'formato': 'A0'}
    for kind, v in (('lamiera', LAM), ('telaio', {}), ('cono', {}), ('piastra', {}), ('zero', {})):
        s = Service()
        chiama(s, 'new_project', kind, v)
        if kind == 'lamiera':
            chiama(s, 'add_flange', 'SM1', 'L1', {'length': '30'})
        chiama(s, 'drawing_fields', atteso='any')
        chiama(s, 'drawing_preview', None, False, atteso='no' if kind == 'zero' else 'ok', nota=kind)
        chiama(s, 'drawing_preview', campi_strani, False, atteso='no' if kind == 'zero' else 'any', nota=kind + ' campi strani')
        for est in ('pdf', 'dxf', 'txt'):
            chiama(s, 'export_drawings', str(TMP / f'tav_{kind}.{est}'), {'formato': 'A4'}, False,
                   atteso='no' if kind == 'zero' else 'any', nota=f'{kind} {est}')
        for fmt in ('A4', 'A3', 'A2'):
            chiama(s, 'drawing_preview', {'formato': fmt}, False, atteso='no' if kind == 'zero' else 'any', nota=f'{kind} {fmt}')


# ====================================================================================== 12. selezione, scena, annulla
@gruppo('Selezione, scena, annulla/ripeti a vuoto')
def g_varie():
    s = Service()
    chiama(s, 'state', atteso='any')
    chiama(s, 'scene', atteso='any')
    chiama(s, 'undo', atteso='no', nota='niente da annullare')
    chiama(s, 'redo', atteso='no', nota='niente da ripetere')
    s = lamiera()
    chiama(s, 'add_flange', 'SM1', 'L1', {'length': '30'})
    for oid, fi, fn in (('body', None, None), ('body', 0, None), ('body', 99999, None), ('body', None, 'SM1/sopra'),
                        ('body', None, 'SM1/FL1/esterno'), ('body', None, 'boh/boh'), ('flange=SM1/FL1', None, None),
                        ('flange=SM1/FL99', None, None), ('boh', None, None), ('S1', None, None), ('SM1', None, None)):
        chiama(s, 'select', oid, fi, fn, atteso='any', nota=f'{oid} {fi} {fn}')
    for _ in range(30):
        if not s.undo().get('ok'):
            break
    for _ in range(30):
        if not s.redo().get('ok'):
            break
    try:
        s.state()
        annota('OK', 'annulla tutto / ripeti tutto')
    except Exception as ex:  # noqa: BLE001
        annota('BUG', 'annulla tutto / ripeti tutto', repr(ex))


def main():
    t0 = time.time()
    for nome, fn in GRUPPI:
        GRUPPO[0] = nome
        print(f'\n=== {nome}', flush=True)
        tg = time.time()
        try:
            fn()
        except Exception as ex:  # noqa: BLE001
            annota('BUG', f'gruppo interrotto: {nome}', ''.join(traceback.format_exception(ex))[-800:])
        print(f'    ({time.time() - tg:.0f} s)', flush=True)
    conta = {}
    for r in RISULTATI:
        conta[r['tipo']] = conta.get(r['tipo'], 0) + 1
    (TMP / 'rapporto.json').write_text(json.dumps(RISULTATI, indent=1), encoding='utf-8')
    print(f'\n{N["chiamate"]} chiamate in {time.time() - t0:.0f} s — ' + ', '.join(f'{k}: {v}' for k, v in sorted(conta.items())))
    print(f'rapporto: {TMP / "rapporto.json"}')


if __name__ == '__main__':
    main()
