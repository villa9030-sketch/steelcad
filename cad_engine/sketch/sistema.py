"""«Sistema il disegno» (05/11, idea da SolidCraft sketch.auto_constrain; niente codice copiato).

Un disegno arrivato da fuori (DXF importato, SVG) ha solo punti: niente orizzontali, verticali, tangenze. Qui si
trovano le relazioni che il disegno ha già quasi esatte e si propongono: l'anteprima dice cosa si mette, si
conferma. Il disegno non si sposta (al massimo di qualche centesimo, per le linee storte di un niente).

- punti uniti: estremità a meno di TOL_PUNTI diventano un punto solo;
- orizzontali / verticali: linee che si scostano di meno di TOL_HV mm da un capo all'altro;
- tangenti: linea e arco (o due archi) che si toccano con la stessa direzione (entro TOL_ANG gradi);
- uguali: linee della stessa lunghezza, archi e cerchi dello stesso raggio (entro TOL_PUNTI).

Un disegno tutto bloccato (com'è arrivato dal DXF) si sblocca: resta fermo un punto solo, il resto si quota.
Quello che sarebbe di troppo (già deciso dalle altre relazioni o dalle quote) non si mette.
"""
from __future__ import annotations

import copy
import math

from .model import ORIGIN, Sketch
from .stato import _sostituisci_punto

TOL_PUNTI = 0.01       # mm
TOL_HV = 0.05          # mm di scostamento da un capo all'altro della linea
TOL_ANG = 0.5          # gradi
TIPI = ('uniti', 'hv', 'tangenti', 'uguali')


def _fissi(sk: Sketch) -> dict:
    return {c['refs'][0]: kid for kid, c in sk.constraints.items() if c['type'] == 'fix' and len(c['refs']) == 1}


def _curve(sk: Sketch, kinds=('line', 'arc', 'circle')) -> dict:
    return {k: e for k, e in sk.entities.items()
            if e['kind'] in kinds and not e.get('construction') and not e.get('ref')}


def _xy(sk, p):
    e = sk.entities[p]
    return e['x'], e['y']


def _bloccati(sk: Sketch) -> list:
    """I blocchi da togliere: solo se il disegno è quasi tutto bloccato (com'arriva da un import), mai i bordi del
    pezzo. Un «fisso» messo a mano su un disegno normale resta."""
    fissi = _fissi(sk)
    punti = {e[x] for e in _curve(sk).values() for x in ('a', 'b', 'start', 'end') if x in e}
    punti.discard(ORIGIN)
    if not punti:
        return []
    bloccati = [p for p in punti if p in fissi and not sk.entities[p].get('ref')]
    return bloccati if len(bloccati) >= 0.8 * len(punti) else []


def _vincolati(sk: Sketch, tipo: str) -> set:
    return {tuple(c['refs']) if len(c['refs']) > 1 else c['refs'][0]
            for c in sk.constraints.values() if c['type'] == tipo}


def trova(sk: Sketch) -> dict:
    """Le proposte sul disegno com'è (coordinate salvate): {'uniti': [(via, resta)], 'hv': [(linea, 'horizontal'|
    'vertical')], 'tangenti': [(a, b)], 'uguali': [(a, b)], 'sblocca': [punti]}."""
    curve = _curve(sk)
    fissi = _fissi(sk)
    # punti uniti: estremità diverse nello stesso posto
    estremi = []
    for k, e in curve.items():
        for x in ('a', 'b', 'start', 'end'):
            if x in e and e[x] not in estremi:
                estremi.append(e[x])
    uniti, preso = [], {}
    cella = max(TOL_PUNTI * 4, 1e-6)
    griglia: dict = {}
    for p in estremi:
        x, y = _xy(sk, p)
        cx, cy = math.floor(x / cella), math.floor(y / cella)
        trovato = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in griglia.get((cx + dx, cy + dy), ()):
                    if math.dist((x, y), _xy(sk, q)) <= TOL_PUNTI:
                        trovato = q
                        break
        if trovato is not None:
            resta = preso.get(trovato, trovato)
            # resta il punto bloccato o l'origine, se c'è
            if p == ORIGIN or (p in fissi and resta not in fissi and resta != ORIGIN):
                resta, p = p, resta
            uniti.append((p, resta))
            preso[p] = resta
        else:
            griglia.setdefault((cx, cy), []).append(p)
    unito = {v: r for v, r in uniti}

    def P(p):
        return _xy(sk, unito.get(p, p))

    # orizzontali e verticali
    hv = []
    gia = _vincolati(sk, 'horizontal') | _vincolati(sk, 'vertical')
    for k, e in curve.items():
        if e['kind'] != 'line' or k in gia:
            continue
        (ax, ay), (bx, by) = P(e['a']), P(e['b'])
        if math.hypot(bx - ax, by - ay) < 10 * TOL_PUNTI:
            continue
        if abs(by - ay) <= TOL_HV and abs(bx - ax) > TOL_HV:
            hv.append((k, 'horizontal'))
        elif abs(bx - ax) <= TOL_HV and abs(by - ay) > TOL_HV:
            hv.append((k, 'vertical'))
    # tangenti: dove una linea e un arco (o due archi) si toccano, con la stessa direzione
    def direzione(k, p):
        """La direzione della curva k nel suo estremo p (verso l'esterno non importa: si confronta la retta)."""
        e = curve[k]
        if e['kind'] == 'line':
            (ax, ay), (bx, by) = P(e['a']), P(e['b'])
            return math.atan2(by - ay, bx - ax)
        cx, cy = P(e['center'])
        x, y = P(p)
        return math.atan2(y - cy, x - cx) + math.pi / 2

    tangenti = []
    gia_t = {frozenset(c['refs']) for c in sk.constraints.values() if c['type'] in ('tangent', 'perpendicular')}
    per_punto: dict = {}
    for k, e in curve.items():
        for x in ('a', 'b', 'start', 'end'):
            if x in e:
                per_punto.setdefault(unito.get(e[x], e[x]), []).append((k, e[x]))
    for p, lst in per_punto.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                (k1, p1), (k2, p2) = lst[i], lst[j]
                if k1 == k2 or 'arc' not in (curve[k1]['kind'], curve[k2]['kind']) or frozenset((k1, k2)) in gia_t:
                    continue
                d = (direzione(k1, p1) - direzione(k2, p2)) % math.pi
                if min(d, math.pi - d) <= math.radians(TOL_ANG):
                    tangenti.append((k1, k2))
    # uguali: stessa lunghezza (linee), stesso raggio (archi e cerchi), a catena
    uguali = []
    gia_u = {frozenset(c['refs']) for c in sk.constraints.values() if c['type'] == 'equal'}
    misure = []
    # una linea attaccata a un arco no: tangenza + punto in comune è un caso in cui il risolutore non vede che
    # «uguale» è già deciso dai raggi, e poi due quote giuste litigavano (prova del raccordo sui 4 spigoli)
    su_arco = {unito.get(e[x], e[x]) for e in curve.values() if e['kind'] == 'arc' for x in ('start', 'end')}
    for k, e in curve.items():
        if e['kind'] == 'line':
            if unito.get(e['a'], e['a']) in su_arco or unito.get(e['b'], e['b']) in su_arco:
                continue
            (ax, ay), (bx, by) = P(e['a']), P(e['b'])
            misure.append(('L', math.hypot(bx - ax, by - ay), k))
        elif e['kind'] == 'circle':
            misure.append(('R', e['r'], k))
        else:
            (cx, cy), (x, y) = P(e['center']), P(e['start'])
            misure.append(('R', math.hypot(x - cx, y - cy), k))
    misure.sort()
    for (t1, v1, k1), (t2, v2, k2) in zip(misure, misure[1:]):
        if t1 == t2 and abs(v1 - v2) <= TOL_PUNTI and v1 > 10 * TOL_PUNTI and frozenset((k1, k2)) not in gia_u:
            uguali.append((k1, k2))
    return {'uniti': uniti, 'hv': hv, 'tangenti': tangenti, 'uguali': uguali, 'sblocca': _bloccati(sk)}


def _metti(sk: Sketch, prop: dict, tipi) -> dict:
    """Mette le proposte scelte sullo sketch (sul posto). Rende {tipo: [id vincoli nuovi]}."""
    nuovi = {t: [] for t in TIPI}
    sblocca = prop.get('sblocca') or []
    if sblocca:
        fissi = _fissi(sk)
        tenere = min(sblocca, key=lambda p: (_xy(sk, p)[0] + _xy(sk, p)[1], p))   # resta fermo il punto in basso a sinistra
        # anche i centri degli archi (l'SVG li porta bloccati): se no la tangenza non può far niente. I centri dei
        # cerchi (i fori) restano dove sono
        centri = [e['center'] for e in _curve(sk, ('arc',)).values()]
        for p in list(sblocca) + centri:
            if p != tenere and p in fissi and fissi[p] in sk.constraints and not sk.entities[p].get('ref'):
                del sk.constraints[fissi[p]]
    if 'uniti' in tipi:
        for via, resta in prop['uniti']:
            if via in sk.entities and resta in sk.entities and via != resta:
                _sostituisci_punto(sk, via, resta)
                nuovi['uniti'].append(via)
    for k, t in prop['hv'] if 'hv' in tipi else ():
        if k in sk.entities:
            nuovi['hv'].append(sk.constrain(t, k, auto=True))
    for a, b in prop['tangenti'] if 'tangenti' in tipi else ():
        if a in sk.entities and b in sk.entities:
            nuovi['tangenti'].append(sk.constrain('tangent', a, b, auto=True))
    for a, b in prop['uguali'] if 'uguali' in tipi else ():
        if a in sk.entities and b in sk.entities:
            nuovi['uguali'].append(sk.constrain('equal', a, b, auto=True))
    return nuovi


def _di_troppo(sk: Sketch, params: dict, candidati: set) -> tuple[set, bool]:
    """Quali dei vincoli candidati sono di troppo o litigano (diagnosi del risolutore). (da togliere, pulito)"""
    from .solver import _build
    s, _ids, tag_of, _v = _build(sk, params, jitter=True)
    d = s.diagnose()
    male = {tag_of[t] for t in list(d.conflicting) + list(d.redundant) if t in tag_of}
    if not male:
        return set(), True
    return male & candidati, False


def prova(sk: Sketch, params: dict | None = None, tipi=TIPI) -> tuple[Sketch, dict]:
    """Lo sketch con le relazioni scelte messe (una copia) e cosa si è messo davvero: {tipo: n, 'sbloccati': n}.
    Le relazioni di troppo si tolgono, a giri, finché il risolutore non è contento."""
    params = params or {}
    nuovo = copy.deepcopy(sk)
    nuovo.__dict__.pop('_ultimi_id', None)
    prop = trova(nuovo)
    nuovi = _metti(nuovo, prop, set(tipi))
    candidati = {k for t in ('hv', 'tangenti', 'uguali') for k in nuovi[t]}
    for _giro in range(8):
        via, pulito = _di_troppo(nuovo, params, candidati)
        if pulito:
            break
        if not via:
            # il risolutore se la prende con vincoli vecchi: si toglie l'ultimo gruppo di nuovi e si riprova
            ultimo = next((t for t in ('uguali', 'tangenti', 'hv') if nuovi[t]), None)
            if ultimo is None:
                break
            via = set(nuovi[ultimo])
        for k in via:
            nuovo.constraints.pop(k, None)
        for t in nuovi:
            if t != 'uniti':
                nuovi[t] = [k for k in nuovi[t] if k not in via]
        candidati -= via
    conti = {t: len(nuovi[t]) for t in TIPI}
    conti['sbloccati'] = max(0, len(prop['sblocca']) - 1)
    return nuovo, {'conti': conti, 'nuovi': nuovi, 'proposte': prop}
