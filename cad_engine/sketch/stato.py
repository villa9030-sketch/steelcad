"""Quanto è deciso il disegno, punto per punto, e dove il contorno resta aperto (05/11, idee da SolidCraft:
sketch.degrees_of_freedom e sketch.loose_ends; niente codice copiato).

- `elementi_liberi`: le linee, gli archi e i cerchi che si possono ancora muovere (mancano misure). Come i CAD seri
  li colorano diversi da quelli già decisi. Si prova punto per punto: se bloccare un punto toglie libertà al
  disegno, quel punto si muoveva ancora.
- `estremita_aperte`: le estremità di linee e archi che non toccano niente (il motivo per cui un profilo non si
  chiude) e le coppie abbastanza vicine da unire con «Chiudi».
- `unisci_estremita`: «Chiudi» le unisce (un punto solo al posto di due).
"""
from __future__ import annotations

import dataclasses
import json
import math

from ..errors import SketchError
from .model import ORIGIN, Sketch

# «Chiudi» unisce solo estremità più vicine di così (mm): una svista di disegno o un DXF un po' sporco, non un
# buco vero. Da decidere con Stefano: si cambia qui.
CHIUDI_TOL = 1.0
# un pezzo di disegno legato con più punti liberi di così: il conto punto per punto costerebbe troppo a ogni
# modifica (si dice solo il totale, le sue linee restano del colore di sempre)
MAX_PUNTI_LIBERI = 80

_MEMO: dict = {}


def _senza_riferimento(sk: Sketch) -> Sketch:
    rif = {k for k, c in sk.constraints.items() if c.get('driven')}
    if not rif:
        return sk
    return dataclasses.replace(sk, constraints={k: c for k, c in sk.constraints.items() if k not in rif})


def elementi_liberi(sk: Sketch, params: dict | None = None, dof: int | None = None):
    """Gli id di linee, archi e cerchi (non di costruzione né bordi del pezzo) che si muovono ancora.
    [] se il disegno è tutto deciso; None se non si sa (disegno troppo grande, o con quote in conflitto)."""
    if dof == 0:
        return []
    params = params or {}
    try:
        chiave = json.dumps([sk.entities, sk.constraints, params], sort_keys=True, default=str)
    except (TypeError, ValueError):
        chiave = None
    if chiave is not None and chiave in _MEMO:
        return list(_MEMO[chiave]) if _MEMO[chiave] is not None else None
    out = _calcola(sk, params)
    if chiave is not None:
        if len(_MEMO) > 64:
            _MEMO.pop(next(iter(_MEMO)))
        _MEMO[chiave] = out
    return list(out) if out is not None else None


def _gruppi(sk: Sketch) -> list:
    """I pezzi indipendenti del disegno: punti legati da linee, archi, cerchi o vincoli. L'origine e i punti bloccati
    non legano niente (non si muovono). Ogni gruppo: (punti, curve, vincoli)."""
    fissi = {c['refs'][0] for c in sk.constraints.values() if c['type'] == 'fix' and len(c['refs']) == 1}
    padre: dict = {}

    def trova(x):
        while padre.setdefault(x, x) != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unisci(a, b):
        ra, rb = trova(a), trova(b)
        if ra != rb:
            padre[ra] = rb

    def nodi(eid):
        """I nodi che muovono un'entità: i suoi punti liberi e, per un cerchio, il suo raggio (l'id del cerchio)."""
        e = sk.entities.get(eid)
        if e is None:
            return []
        if e['kind'] == 'point':
            return [] if eid == ORIGIN or eid in fissi else [eid]
        out = [e[k] for k in ('a', 'b', 'center', 'start', 'end') if k in e and e[k] != ORIGIN and e[k] not in fissi]
        if e['kind'] == 'circle':
            out.append(eid)
        return out

    for k, e in sk.entities.items():
        n = nodi(k)
        for x in n:
            trova(x)
        for x in n[1:]:
            unisci(n[0], x)
    vincoli_di: dict = {}
    for kid, c in sk.constraints.items():
        n = [x for r in c['refs'] for x in nodi(r)]
        for x in n[1:]:
            unisci(n[0], x)
        if n:
            vincoli_di.setdefault(n[0], []).append(kid)
    gruppi: dict = {}
    for x in padre:
        gruppi.setdefault(trova(x), set()).add(x)
    out = []
    for radice, membri in gruppi.items():
        vinc = [kid for m in membri for kid in vincoli_di.get(m, [])]
        out.append((membri, vinc))
    return out


def _sotto_sketch(sk: Sketch, membri: set, vincoli: list) -> Sketch:
    """Il gruppo da solo: i suoi punti e curve, i vincoli che lo toccano e i punti fissi che questi citano."""
    usati = set()
    for k, e in sk.entities.items():
        if k in membri or any(e.get(x) in membri for x in ('a', 'b', 'center', 'start', 'end')):
            usati.add(k)
    for kid in vincoli:
        usati.update(r for r in sk.constraints[kid]['refs'] if r in sk.entities)
    for k in list(usati):
        e = sk.entities[k]
        usati.update(e[x] for x in ('a', 'b', 'center', 'start', 'end') if x in e)
        if e['kind'] == 'text':
            usati.add(e['center'])
    ent = {k: e for k, e in sk.entities.items() if k in usati}
    vin = {kid: sk.constraints[kid] for kid in vincoli}
    for k in usati:                       # i blocchi dei punti fissi citati
        for kid, c in sk.constraints.items():
            if c['type'] == 'fix' and c['refs'] == [k]:
                vin[kid] = c
    return Sketch(sk.id, sk.name, sk.plane, ent, vin)


_MEMO_GRUPPI: dict = {}


def _calcola(sk: Sketch, params: dict):
    sk = _senza_riferimento(sk)
    curve = {k: e for k, e in sk.entities.items()
             if e['kind'] in ('line', 'arc', 'circle') and not e.get('construction') and not e.get('ref')}
    if not curve:
        return []
    mobili, ignoti = set(), set()
    for membri, vincoli in _gruppi(sk):
        punti = [m for m in membri if sk.entities[m]['kind'] == 'point']
        if len(punti) > MAX_PUNTI_LIBERI:
            ignoti |= membri
            continue
        sub = _sotto_sketch(sk, membri, vincoli)
        try:
            chiave = json.dumps([sub.entities, sub.constraints, params, sorted(membri)], sort_keys=True, default=str)
        except (TypeError, ValueError):
            chiave = None
        r = _MEMO_GRUPPI.get(chiave) if chiave is not None else None
        if r is None:
            r = _mobili_del_gruppo(sub, params, membri)
            if chiave is not None:
                if len(_MEMO_GRUPPI) > 20000:
                    _MEMO_GRUPPI.clear()
                _MEMO_GRUPPI[chiave] = r
        if r is False:
            return None                       # quote in conflitto o di troppo: prima si sistemano quelle
        mobili |= r
    liberi = []
    for k, e in curve.items():
        nodi = [e[x] for x in ('a', 'b', 'center', 'start', 'end') if x in e] + ([k] if e['kind'] == 'circle' else [])
        if any(n in ignoti for n in nodi):
            continue                          # non si sa: resta del colore di sempre
        if any(n in mobili for n in nodi):
            liberi.append(k)
    return liberi


def _mobili_del_gruppo(sub: Sketch, params: dict, membri: set):
    """I nodi del gruppo (punti, raggi dei cerchi) che si muovono ancora; False se il gruppo ha quote che litigano."""
    from .solver import _build
    try:
        s, (pid, _lid, cid_, _aid), _tag, _val = _build(sub, params, jitter=True)
        d0 = s.diagnose()
    except (SketchError, KeyError, ValueError):
        return False
    if list(d0.conflicting) or list(d0.redundant):
        return False
    base = d0.dof
    if base == 0:
        return set()
    mobili = set()
    for p in membri:
        if p in pid:
            x, y = s.get_point(pid[p])
            t1 = s.coordinate_x(pid[p], s.add_param(x, fixed=True))
            t2 = s.coordinate_y(pid[p], s.add_param(y, fixed=True))
            dd = s.diagnose().dof
            s.clear_by_tag(t1)
            s.clear_by_tag(t2)
        elif p in cid_:
            t = s.circle_radius(cid_[p], s.add_param(s.get_circle(cid_[p]).radius, fixed=True))
            dd = s.diagnose().dof
            s.clear_by_tag(t)
        else:
            continue
        if dd < base:
            mobili.add(p)
    return mobili


def frase_misure(state: str, dof: int) -> str:
    """La scritta sempre a vista: «Tutto definito», «Manca 1 misura», «Mancano 3 misure»."""
    if state == 'completo':
        return 'Tutto definito'
    if state == 'parziale':
        return 'Manca 1 misura' if dof == 1 else f'Mancano {dof} misure'
    if state in ('sovra-vincolato', 'ridondante'):
        return 'Misure di troppo'
    return 'Da sistemare'


# ============================================================================ estremità aperte
def _estremi(sk: Sketch, ss) -> list:
    """(id curva, id punto, (x, y)) per ogni estremità di linee e archi disegnati (non guide, non bordi)."""
    out = []
    for k, (a, b) in ss.lines.items():
        e = sk.entities[k]
        if e.get('construction') or e.get('ref') or a == b:
            continue
        out += [(k, a, ss.points[a]), (k, b, ss.points[b])]
    for k, (_c, a, b, _r) in ss.arcs.items():
        e = sk.entities[k]
        if e.get('construction') or e.get('ref'):
            continue
        out += [(k, a, ss.points[a]), (k, b, ss.points[b])]
    return out


def _dist_curva(ss, sk, k, q) -> float:
    """Distanza del punto q dalla linea / arco / cerchio k (nel tratto, non sulla retta)."""
    if k in ss.lines:
        (ax, ay), (bx, by) = (ss.points[x] for x in ss.lines[k])
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L2))
        return math.hypot(ax + t * dx - q[0], ay + t * dy - q[1])
    if k in ss.circles:
        c, r = ss.circles[k]
        cx, cy = ss.points[c]
        return abs(math.hypot(q[0] - cx, q[1] - cy) - r)
    if k in ss.arcs:
        c, a, b, r = ss.arcs[k]
        (cx, cy), (ax, ay), (bx, by) = ss.points[c], ss.points[a], ss.points[b]
        t0, t1, t = (math.atan2(y - cy, x - cx) for x, y in ((ax, ay), (bx, by), q))
        giro = lambda u: (u - t0) % (2 * math.pi)  # noqa: E731
        if giro(t) <= giro(t1):
            return abs(math.hypot(q[0] - cx, q[1] - cy) - r)
        return min(math.dist(q, (ax, ay)), math.dist(q, (bx, by)))
    return math.inf


def estremita_aperte(sk: Sketch, ss, tol: float = CHIUDI_TOL) -> dict:
    """{'aperte': [{'pid', 'xy', 'curva'}], 'coppie': [{'a', 'b', 'xy_a', 'xy_b', 'dist'}]}.
    Aperta = l'estremità non tocca nessun'altra linea, arco o cerchio (nemmeno i bordi del pezzo)."""
    estremi = _estremi(sk, ss)
    scala = max([1.0] + [abs(c) for *_, q in estremi for c in q])
    vicino = 1e-6 * scala + 1e-7
    curve = [k for k in list(ss.lines) + list(ss.arcs) + list(ss.circles)
             if not (sk.entities[k].get('construction') and not sk.entities[k].get('ref'))]
    # griglia per non confrontare tutti con tutti (serie grandi)
    cella = max(tol, 1.0)
    griglia: dict = {}
    for i, (_k, _p, q) in enumerate(estremi):
        griglia.setdefault((math.floor(q[0] / cella), math.floor(q[1] / cella)), []).append(i)

    def vicini(q):
        cx, cy = math.floor(q[0] / cella), math.floor(q[1] / cella)
        return [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in griglia.get((cx + dx, cy + dy), ())]

    aperte = []
    for i, (k, p, q) in enumerate(estremi):
        if any(j != i and (estremi[j][1] == p or math.dist(estremi[j][2], q) <= vicino) for j in vicini(q)):
            continue
        # tocca una linea, un arco o un cerchio a metà (anche un bordo arancio del pezzo)? allora non è libera
        if any(c != k and _dist_curva(ss, sk, c, q) <= vicino for c in curve):
            continue
        if any(aperta['pid'] == p for aperta in aperte):
            continue
        aperte.append({'pid': p, 'xy': [q[0], q[1]], 'curva': k})
    # le coppie da unire: le più vicine prima, ogni estremità una volta sola
    cand = []
    for i, a in enumerate(aperte):
        for b in aperte[i + 1:]:
            d = math.dist(a['xy'], b['xy'])
            if d <= tol and a['curva'] != b['curva']:
                cand.append((d, a, b))
    cand.sort(key=lambda x: x[0])
    usate, coppie = set(), []
    for d, a, b in cand:
        if a['pid'] in usate or b['pid'] in usate:
            continue
        usate |= {a['pid'], b['pid']}
        coppie.append({'a': a['pid'], 'b': b['pid'], 'xy_a': a['xy'], 'xy_b': b['xy'], 'dist': round(d, 4)})
    return {'aperte': aperte, 'coppie': coppie}


def _sostituisci_punto(sk: Sketch, via: str, resta: str) -> None:
    """Il punto `via` diventa `resta` dappertutto (curve, vincoli, quote); `via` si toglie."""
    for e in sk.entities.values():
        for k in ('a', 'b', 'center', 'start', 'end'):
            if e.get(k) == via:
                e[k] = resta
    for kid in list(sk.constraints):
        c = sk.constraints[kid]
        if via not in c['refs']:
            continue
        refs = [resta if r == via else r for r in c['refs']]
        if c['type'] in ('fix', 'coincident') and (c['type'] == 'fix' or refs[0] == refs[1]):
            del sk.constraints[kid]                   # il blocco di quel punto (o la coincidenza con sé stesso): via
            continue
        if c['type'] in ('distance', 'hdistance', 'vdistance') and refs[0] == refs[1]:
            del sk.constraints[kid]
            continue
        c['refs'] = refs
    sk.entities.pop(via, None)


def unisci_estremita(sk: Sketch, coppie: list) -> list:
    """«Chiudi»: ogni coppia diventa un punto solo, a metà strada (un punto bloccato resta dov'è).
    Le linee di lunghezza zero che ne nascono si tolgono. Rende le coppie unite."""
    fissi = {c['refs'][0] for c in sk.constraints.values() if c['type'] == 'fix' and len(c['refs']) == 1}
    fatte = []
    for c in coppie:
        a, b = c['a'], c['b']
        if a not in sk.entities or b not in sk.entities or a == b:
            continue
        # resta l'origine o il punto bloccato, se c'è
        resta, via = (b, a) if b == ORIGIN or (b in fissi and a not in fissi and a != ORIGIN) else (a, b)
        pa, pb = sk.entities[resta], sk.entities[via]
        if resta not in fissi and resta != ORIGIN:
            if via in fissi:
                pa['x'], pa['y'] = pb['x'], pb['y']
            else:
                pa['x'], pa['y'] = (pa['x'] + pb['x']) / 2, (pa['y'] + pb['y']) / 2
        _sostituisci_punto(sk, via, resta)
        fatte.append(c)
    for k in [k for k, e in sk.entities.items() if e['kind'] == 'line' and e['a'] == e['b']]:
        del sk.entities[k]
        for kid in [kid for kid, c in sk.constraints.items() if k in c['refs']]:
            del sk.constraints[kid]
    return fatte
