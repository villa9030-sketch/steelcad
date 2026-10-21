"""Adattatore verso planegcs (il PlaneGCS di FreeCAD) e stato dello sketch in parole semplici.

Funzione pura: dalla definizione dello sketch e dai parametri del documento
a un `SolvedSketch` (coordinate risolte + stato). La definizione non cambia.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import planegcs as gcs

from ..errors import SketchError
from ..expressions import evaluate
from ..units import cap, TOL, rad
from .model import DIMENSIONS, ORIGIN, Sketch

FULLY, UNDER, OVER, REDUNDANT, FAILED = 'completo', 'parziale', 'sovra-vincolato', 'ridondante', 'non risolto'


@dataclass
class SketchStatus:
    state: str                 # completo | parziale | sovra-vincolato | ridondante | non risolto
    dof: int
    message: str
    conflicting: list = field(default_factory=list)   # id dei vincoli/quote coinvolti
    redundant: list = field(default_factory=list)

    @property
    def ok_for_features(self) -> bool:
        """Si può costruire geometria? Sì se risolto (anche se non del tutto vincolato)."""
        return self.state in (FULLY, UNDER)

    def to_dict(self) -> dict:
        return {'state': self.state, 'dof': self.dof, 'message': self.message,
                'conflicting': self.conflicting, 'redundant': self.redundant}


@dataclass
class SolvedSketch:
    sketch: Sketch
    points: dict          # id -> (x, y)
    circles: dict         # id -> (center_id, r)
    arcs: dict            # id -> (center_id, start_id, end_id, r)
    lines: dict           # id -> (a_id, b_id)
    status: SketchStatus
    values: dict          # id quota -> valore numerico usato

    def xy(self, pid: str) -> tuple[float, float]:
        return self.points[pid]


def _value(sk: Sketch, cid: str, c: dict, params: dict) -> float:
    return evaluate(c['value'], params, what=f'valore della quota {cid}')


_MEMORIA: dict = {}


def solve(sk: Sketch, params: dict | None = None) -> SolvedSketch:
    """Risolve lo sketch. Lo stesso disegno con gli stessi parametri dà la stessa soluzione: la si ricorda
    (una modifica nell'interfaccia risolveva lo stesso sketch 3 volte: prima, dopo, nella ricostruzione)."""
    import dataclasses
    import json
    params = params or {}
    try:
        chiave = json.dumps([sk.plane, sk.entities, sk.constraints, params], sort_keys=True, default=str)
    except (TypeError, ValueError):
        chiave = None
    if chiave is not None and chiave in _MEMORIA:
        return dataclasses.replace(_MEMORIA[chiave], sketch=sk)
    rif = {k: c for k, c in sk.constraints.items() if c.get('driven')}
    if rif:                                     # le quote di riferimento: si risolve senza, poi si misurano
        senza = dataclasses.replace(sk, constraints={k: c for k, c in sk.constraints.items() if k not in rif})
        out = solve(senza, params)
        valori = dict(out.values)
        for k, c in rif.items():
            try:
                valori[k] = misura(out, c)
            except (KeyError, ZeroDivisionError):
                valori[k] = c['value'] if isinstance(c['value'], (int, float)) else 0.0
        out = dataclasses.replace(out, sketch=sk, values=valori)
        if chiave is not None:
            _MEMORIA[chiave] = out
        return out
    out = _solve_a_blocchi(sk, params) if len(sk.constraints) > _SOGLIA_BLOCCHI else None
    if out is None:
        out = _solve(sk, params)
    if chiave is not None:
        if len(_MEMORIA) > 64:
            _MEMORIA.pop(next(iter(_MEMORIA)))
        _MEMORIA[chiave] = out
    return out


def misura(ss: 'SolvedSketch', c: dict) -> float:
    """La misura che una quota leggerebbe sul disegno risolto (per le quote di riferimento)."""
    t, refs, P = c['type'], c['refs'], ss.points
    if t == 'length':
        a, b = ss.lines[refs[0]]
        return math.dist(P[a], P[b])
    if t in ('diameter', 'radius'):
        r = ss.circles[refs[0]][1] if refs[0] in ss.circles else ss.arcs[refs[0]][3]
        return 2 * r if t == 'diameter' else r
    if t == 'distance':
        return math.dist(P[refs[0]], P[refs[1]])
    if t == 'hdistance':
        return P[refs[1]][0] - P[refs[0]][0]
    if t == 'vdistance':
        return P[refs[1]][1] - P[refs[0]][1]
    if t == 'pldistance':
        (ax, ay), (bx, by) = (P[x] for x in ss.lines[refs[1]])
        px, py = P[refs[0]]
        return abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / math.hypot(bx - ax, by - ay)
    if t == 'angle':
        (a1, b1), (a2, b2) = (tuple(P[x] for x in ss.lines[r]) for r in refs[:2])
        u = math.atan2(b1[1] - a1[1], b1[0] - a1[0]) - math.atan2(b2[1] - a2[1], b2[0] - a2[0])
        g = abs(math.degrees(u)) % 180
        return min(g, 180 - g) if c.get('value', 0) <= 90 else max(g, 180 - g)
    raise KeyError(t)


# ============================================================================ a blocchi
# Uno sketch grande (una serie di 75 asole: 760 vincoli) risolto e diagnosticato tutto insieme costava secondi,
# e cresceva col cubo. Ma le copie di una serie sono attaccate al resto per un punto solo: si divide lo sketch nei
# suoi blocchi (componenti biconnesse, tagliate sui punti) e si risolve un blocco alla volta, coi punti di
# aggancio già risolti tenuti fissi. Se ogni blocco è pulito (niente vincoli doppi o in conflitto) il risultato è
# lo stesso del calcolo intero; altrimenti si rifà il calcolo intero, che dà i messaggi giusti.
_SOGLIA_BLOCCHI = 60


def _fissi_di(sk: Sketch) -> set:
    fissi = {c['refs'][0] for c in sk.constraints.values() if c['type'] == 'fix' and len(c['refs']) == 1
             and sk.entities.get(c['refs'][0], {}).get('kind') == 'point'}
    return fissi | {ORIGIN}


def _riferimenti(sk: Sketch, e: dict) -> list:
    return [e[k] for k in ('a', 'b', 'center', 'start', 'end') if k in e]


def _blocchi(sk: Sketch) -> list:
    """I blocchi dello sketch: [(entità, vincoli)]. Nodi: entità non fisse e vincoli; i punti fissi non
    collegano niente (sono costanti)."""
    fissi = _fissi_di(sk)
    adj: dict = {}

    # vicini come dizionari (insiemi ordinati): tutto segue l'ordine del disegno, mai quello casuale degli insiemi
    # di Python, che cambia a ogni avvio (uno sketch non del tutto vincolato veniva risolto in modo un po' diverso
    # ogni volta che si apriva il file)
    def lega(u, v):
        adj.setdefault(u, {})[v] = None
        adj.setdefault(v, {})[u] = None

    for eid, e in sk.entities.items():
        if e['kind'] == 'point' and eid in fissi:
            continue
        adj.setdefault(('e', eid), {})
        if e['kind'] != 'point':
            for p in _riferimenti(sk, e):
                if p not in fissi:
                    lega(('e', eid), ('e', p))
    for cid, c in sk.constraints.items():
        if c['type'] == 'fix' and len(c['refs']) == 1 and c['refs'][0] in fissi:
            continue
        adj.setdefault(('c', cid), {})
        for r in c['refs']:
            if r in sk.entities and not (sk.entities[r]['kind'] == 'point' and r in fissi):
                lega(('c', cid), ('e', r))
    # componenti biconnesse (Tarjan, senza ricorsione: gli sketch grandi hanno migliaia di nodi)
    num, low, comps, pila_archi, cont = {}, {}, [], [], [0]
    for radice in adj:
        if radice in num:
            continue
        cont[0] += 1
        num[radice] = low[radice] = cont[0]
        if not adj[radice]:
            comps.append({radice})
            continue
        pila = [(radice, None, iter(adj[radice]))]
        while pila:
            u, padre, it = pila[-1]
            avanti = False
            for v in it:
                if v == padre:
                    continue
                if v not in num:
                    pila_archi.append((u, v))
                    cont[0] += 1
                    num[v] = low[v] = cont[0]
                    pila.append((v, u, iter(adj[v])))
                    avanti = True
                    break
                if num[v] < num[u]:
                    pila_archi.append((u, v))
                    low[u] = min(low[u], num[v])
            if avanti:
                continue
            pila.pop()
            if padre is not None:
                low[padre] = min(low[padre], low[u])
                if low[u] >= num[padre]:                     # padre è un punto di taglio (o la radice)
                    comp = set()
                    while pila_archi:
                        a, b = pila_archi.pop()
                        comp |= {a, b}
                        if (a, b) == (padre, u):
                            break
                    comps.append(comp)
    # si taglia solo sui punti: i blocchi che condividono una linea, un arco o un vincolo si riuniscono
    capo = list(range(len(comps)))

    def trova(i):
        while capo[i] != i:
            capo[i] = capo[capo[i]]
            i = capo[i]
        return i

    dove: dict = {}
    for i, comp in enumerate(comps):
        for n in comp:
            if n[0] == 'c' or sk.entities[n[1]]['kind'] != 'point':
                if n in dove:
                    capo[trova(i)] = trova(dove[n])
                else:
                    dove[n] = i
    uniti: dict = {}
    for i, comp in enumerate(comps):
        uniti.setdefault(trova(i), set()).update(comp)
    return [({n[1] for n in c if n[0] == 'e'}, {n[1] for n in c if n[0] == 'c'}) for c in uniti.values()]


def _unisci(blocchi: list, gruppi: list) -> list:
    """Unisce i blocchi indicati (ogni gruppo: indici da fondere in uno)."""
    capo = list(range(len(blocchi)))

    def trova(i):
        while capo[i] != i:
            capo[i] = capo[capo[i]]
            i = capo[i]
        return i

    for g in gruppi:
        for i in g[1:]:
            capo[trova(i)] = trova(g[0])
    out: dict = {}
    for i, (ents, vinc) in enumerate(blocchi):
        e, v = out.setdefault(trova(i), (set(), set()))
        e |= ents
        v |= vinc
    return list(out.values())


def _solve_a_blocchi(sk: Sketch, params: dict) -> SolvedSketch | None:
    try:
        blocchi = _blocchi(sk)
    except Exception:  # noqa: BLE001 - nel dubbio, il calcolo intero
        return None
    fissi = _fissi_di(sk)
    # i blocchi che toccano un solo punto (le quote di posizione di un punto dall'origine, una per X e una per Y)
    # vanno insieme: separate, la seconda troverebbe il punto già fermo e sembrerebbe superflua
    pendenti: dict = {}
    for i, (ents, _) in enumerate(blocchi):
        if len(ents) == 1:
            pendenti.setdefault(next(iter(ents)), []).append(i)
    blocchi = _unisci(blocchi, list(pendenti.values()))
    for _giro in range(12):
        if len(blocchi) < 2:
            return None
        esito = _risolvi_blocchi(sk, params, blocchi, fissi)
        if isinstance(esito, SolvedSketch):
            return esito
        if esito is None:
            return None
        # il blocco esito non è pulito da solo: si unisce a tutti i blocchi con cui ha punti in comune e si riprova
        ents = blocchi[esito][0]
        vicini = [esito] + [j for j, (e2, _) in enumerate(blocchi) if j != esito and e2 & ents]
        if len(vicini) == 1:
            return None
        blocchi = _unisci(blocchi, [vicini])
    return None


def _risolvi_blocchi(sk: Sketch, params: dict, blocchi: list, fissi: set):
    """Risolve i blocchi in ordine. Dà la soluzione, oppure l'indice del blocco non pulito (None: errore vero)."""
    # ordine: prima i blocchi ancorati ai punti fissi (le quote dall'origine o dai bordi del pezzo), poi in
    # larghezza: così ogni blocco trova già risolti i punti con cui si aggancia
    di_entita: dict = {}
    for i, (ents, _) in enumerate(blocchi):
        for e in ents:
            di_entita.setdefault(e, []).append(i)

    def ancorato(i):
        return sum(1 for c in blocchi[i][1] for r in sk.constraints[c]['refs'] if r in fissi)

    pos = {e: k for k, e in enumerate(sk.entities)}
    sorgenti = sorted((i for i in range(len(blocchi)) if ancorato(i)), key=lambda i: -ancorato(i))
    ordine, visti, coda = [], set(sorgenti), list(sorgenti)
    while len(ordine) < len(blocchi):
        if not coda:
            altro = max((i for i in range(len(blocchi)) if i not in visti), key=lambda i: len(blocchi[i][1]))
            visti.add(altro)
            coda.append(altro)
        i = coda.pop(0)
        ordine.append(i)
        for e in sorted(blocchi[i][0], key=pos.get):
            for j in di_entita[e]:
                if j not in visti:
                    visti.add(j)
                    coda.append(j)
    punti, cerchi, archi, linee, valori, dof = {}, {}, {}, {}, {}, 0
    for i in ordine:
        ents, vinc = blocchi[i]
        usati = set(ents)
        for e in ents:
            usati.update(_riferimenti(sk, sk.entities[e]))
        for c in vinc:
            usati.update(r for r in sk.constraints[c]['refs'] if r in sk.entities)
        for e in list(usati):                              # i punti delle linee e degli archi citati dai vincoli
            usati.update(_riferimenti(sk, sk.entities[e]))
        entita, vincoli = {}, {c: v for c, v in sk.constraints.items() if c in vinc}
        for e in (x for x in sk.entities if x in usati):
            d = dict(sk.entities[e])
            if d['kind'] == 'point' and e != ORIGIN and (e in fissi or e in punti or e not in ents):
                if e in punti:                               # già risolto in un blocco prima: qui è fisso
                    d['x'], d['y'] = punti[e]
                vincoli[f'_fisso_{e}'] = {'type': 'fix', 'refs': [e]}
            entita[e] = d
        sub = Sketch(sk.id, sk.name, sk.plane, entita, vincoli)
        try:
            r = _solve(sub, params)
        except SketchError:
            return None                                      # il calcolo intero dirà l'errore giusto
        if r.status.state in (OVER, REDUNDANT):
            return i
        if r.status.state not in (FULLY, UNDER):
            return None
        for k, v in r.points.items():
            punti.setdefault(k, v)
        cerchi.update({k: v for k, v in r.circles.items() if k in ents})
        archi.update({k: v for k, v in r.arcs.items() if k in ents})
        linee.update({k: v for k, v in r.lines.items() if k in ents})
        valori.update(r.values)
        dof += r.status.dof
    for e, d in sk.entities.items():                         # punti isolati o fissi non toccati da nessun blocco
        if d['kind'] == 'point' and e not in punti:
            punti[e] = (d['x'], d['y'])
    return SolvedSketch(sk, punti, cerchi, archi, linee, _status(sk, dof, [], [], valori), valori)


def _solve(sk: Sketch, params: dict) -> SolvedSketch:
    # La diagnosi (gradi di libertà, vincoli superflui o in conflitto) si fa su
    # una copia con i punti spostati di pochissimo: se il disegno soddisfa già
    # alla perfezione i vincoli, planegcs vedrebbe superflui vincoli che servono.
    # La soluzione si calcola sempre sul disegno originale.
    dg, _, tag_of_d, values = _build(sk, params, jitter=True)
    diag = dg.diagnose()
    conflict = [tag_of_d[t] for t in diag.conflicting if t in tag_of_d]
    redundant = [tag_of_d[t] for t in diag.redundant if t in tag_of_d]
    status = _status(sk, diag.dof, conflict, redundant, values)
    s, (pid, lid, cid_, aid), _, _ = _build(sk, params, jitter=False)
    if status.state in (OVER, REDUNDANT):
        return _result(sk, s, pid, lid, cid_, aid, status, values, solved=False)
    res = s.solve()
    if res not in (gcs.SolveStatus.Success, gcs.SolveStatus.Converged):
        status = SketchStatus(FAILED, diag.dof,
                              'Con queste quote lo sketch non si può costruire. Controlla che i valori siano '
                              'possibili, per esempio un foro più grande della piastra o un angolo impossibile.')
        return _result(sk, s, pid, lid, cid_, aid, status, values, solved=False)
    return _result(sk, s, pid, lid, cid_, aid, status, values, solved=True)


def _jitter(eid: str, scale: float) -> tuple[float, float]:
    """Spostamento piccolo e deterministico (uguale a ogni esecuzione)."""
    h = sum((i + 1) * ord(ch) for i, ch in enumerate(eid))
    return (math.sin(h) * 1e-3 * scale, math.cos(h * 1.7) * 1e-3 * scale)


def _build(sk: Sketch, params: dict, jitter: bool):
    s = gcs.Sketch()
    pid, lid, cid_, aid = {}, {}, {}, {}
    tag_of = {}          # tag planegcs -> id vincolo nostro
    values = {}

    def add(tag, cid):
        tag_of[int(tag)] = cid

    scale = max([1.0] + [abs(e[k]) for e in sk.entities.values() if e['kind'] == 'point' for k in ('x', 'y')])
    # i punti con un vincolo "fisso" (i bordi arancio del pezzo, a decine) entrano già fissi: niente incognite né
    # equazioni, il risolutore e la diagnosi vanno molto più veloci
    fissi = {c['refs'][0]: kid for kid, c in sk.constraints.items() if c['type'] == 'fix' and len(c['refs']) == 1
             and sk.entities.get(c['refs'][0], {}).get('kind') == 'point'}
    # --- geometria
    for eid, e in sk.entities.items():
        if e['kind'] == 'point':
            if eid == ORIGIN:
                pid[eid] = s.add_fixed_point(0.0, 0.0)
            elif eid in fissi:
                pid[eid] = s.add_fixed_point(e['x'], e['y'])
            else:
                dx, dy = _jitter(eid, scale) if jitter else (0.0, 0.0)
                pid[eid] = s.add_point(e['x'] + dx, e['y'] + dy)
    for eid, e in sk.entities.items():
        k = e['kind']
        if k == 'line':
            lid[eid] = s.add_line(pid[e['a']], pid[e['b']])
        elif k == 'circle':
            cid_[eid] = s.add_circle(pid[e['center']], s.add_param(e['r']))
        elif k == 'arc':
            c, a, b = (s.get_point(pid[e[x]]) for x in ('center', 'start', 'end'))
            r = math.hypot(a[0] - c[0], a[1] - c[1])
            t0 = math.atan2(a[1] - c[1], a[0] - c[0])
            t1 = math.atan2(b[1] - c[1], b[0] - c[0])
            while t1 <= t0:
                t1 += 2 * math.pi
            aid[eid] = s.add_arc_cse(pid[e['center']], pid[e['start']], pid[e['end']], r, t0, t1)

    def curve(ref):
        k = sk.entities[ref]['kind']
        return k, {'line': lid, 'circle': cid_, 'arc': aid}.get(k, {}).get(ref)

    # --- vincoli e quote
    for kid, c in sk.constraints.items():
        t, refs = c['type'], c['refs']
        try:
            if t == 'coincident':
                add(s.coincident(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'horizontal':
                if len(refs) == 1:
                    add(s.horizontal(lid[refs[0]]), kid)
                else:
                    add(s.horizontal_points(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'vertical':
                if len(refs) == 1:
                    add(s.vertical(lid[refs[0]]), kid)
                else:
                    add(s.vertical_points(pid[refs[0]], pid[refs[1]]), kid)
            elif t == 'parallel':
                add(s.parallel(lid[refs[0]], lid[refs[1]]), kid)
            elif t == 'perpendicular':
                add(s.perpendicular(lid[refs[0]], lid[refs[1]]), kid)
            elif t == 'tangent':
                (k1, g1), (k2, g2) = curve(refs[0]), curve(refs[1])
                pair = {k1, k2}
                if k1 == 'line' and k2 == 'arc':
                    add(s.tangent_line_arc(g1, g2), kid)
                elif k1 == 'arc' and k2 == 'line':
                    add(s.tangent_line_arc(g2, g1), kid)
                elif k1 == 'line' and k2 == 'circle':
                    add(s.tangent_line_circle(g1, g2), kid)
                elif k1 == 'circle' and k2 == 'line':
                    add(s.tangent_line_circle(g2, g1), kid)
                elif pair == {'circle'}:
                    add(s.tangent_circle_circle(g1, g2), kid)
                elif pair == {'arc'}:
                    add(s.tangent_arc_arc(g1, g2), kid)
                elif pair == {'circle', 'arc'}:
                    c_, a_ = (g1, g2) if k1 == 'circle' else (g2, g1)
                    add(s.tangent_circle_arc(c_, a_), kid)
                else:
                    raise SketchError('La tangenza si mette tra linee, archi e cerchi.')
            elif t == 'equal':
                (k1, g1), (k2, g2) = curve(refs[0]), curve(refs[1])
                if k1 == k2 == 'line':
                    add(s.equal_length(g1, g2), kid)
                elif k1 == k2 == 'circle':
                    add(s.equal_radius_cc(g1, g2), kid)
                elif k1 == k2 == 'arc':
                    add(s.equal_radius_aa(g1, g2), kid)
                elif {k1, k2} == {'circle', 'arc'}:
                    c_, a_ = (g1, g2) if k1 == 'circle' else (g2, g1)
                    add(s.equal_radius_ca(c_, a_), kid)
                else:
                    raise SketchError('"Uguale" vale tra due linee (lunghezza) o tra cerchi e archi (raggio).')
            elif t == 'concentric':
                c1 = sk.entities[refs[0]]['center']
                c2 = sk.entities[refs[1]]['center']
                add(s.coincident(pid[c1], pid[c2]), kid)
            elif t == 'symmetric':
                k3 = sk.entities[refs[2]]['kind']
                if k3 == 'point':
                    add(s.symmetric_point(pid[refs[0]], pid[refs[1]], pid[refs[2]]), kid)
                else:
                    add(s.symmetric_line(pid[refs[0]], pid[refs[1]], lid[refs[2]]), kid)
            elif t == 'on_line':
                # "sulla linea" vale anche per cerchi e archi: il punto resta sul bordo
                k2 = sk.entities[refs[1]]['kind']
                if k2 == 'circle':
                    add(s.point_on_circle(pid[refs[0]], cid_[refs[1]]), kid)
                elif k2 == 'arc':
                    add(s.point_on_arc(pid[refs[0]], aid[refs[1]]), kid)
                else:
                    add(s.point_on_line(pid[refs[0]], lid[refs[1]]), kid)
            elif t == 'fix' and fissi.get(refs[0]) == kid:
                continue                                  # già fisso come punto
            elif t == 'fix':
                e = sk.entities[refs[0]]
                add(s.coordinate_x(pid[refs[0]], s.add_param(e['x'], fixed=True)), kid)
                add(s.coordinate_y(pid[refs[0]], s.add_param(e['y'], fixed=True)), kid)
            elif t in DIMENSIONS:
                v = _value(sk, kid, c, params)
                values[kid] = v
                if t in ('distance', 'length', 'diameter', 'radius', 'pldistance') and v <= 0:
                    raise SketchError(f'{cap(sk.describe_constraint(kid, v))} deve essere maggiore di zero.',
                                      code='quota_non_valida')
                if t == 'distance':
                    add(s.p2p_distance(pid[refs[0]], pid[refs[1]], s.add_param(v, fixed=True)), kid)
                elif t == 'length':
                    e = sk.entities[refs[0]]
                    add(s.p2p_distance(pid[e['a']], pid[e['b']], s.add_param(v, fixed=True)), kid)
                elif t == 'pldistance':
                    add(s.p2l_distance(pid[refs[0]], lid[refs[1]], s.add_param(v, fixed=True)), kid)
                elif t in ('hdistance', 'vdistance'):
                    i = 0 if t == 'hdistance' else 1
                    p1 = s.get_point_param_ids(pid[refs[0]])[i]
                    p2 = s.get_point_param_ids(pid[refs[1]])[i]
                    add(s.difference(p1, p2, s.add_param(v, fixed=True)), kid)
                elif t == 'angle':
                    add(s.l2l_angle(lid[refs[0]], lid[refs[1]], s.add_param(rad(v), fixed=True)), kid)
                elif t in ('diameter', 'radius'):
                    r = v / 2 if t == 'diameter' else v
                    k, g = curve(refs[0])
                    if k == 'circle':
                        add(s.circle_radius(g, s.add_param(r, fixed=True)), kid)
                    elif k == 'arc':
                        add(s.arc_radius(g, s.add_param(r, fixed=True)), kid)
                    else:
                        raise SketchError(f'{cap(DIMENSIONS[t])} si mette su un cerchio o un arco.')
        except KeyError as ex:
            raise SketchError(f'{sk.describe_constraint(kid)} usa un elemento che non va bene ({ex}).',
                              code='vincolo_non_valido') from None

    return s, (pid, lid, cid_, aid), tag_of, values


def _status(sk, dof, conflict, redundant, values) -> SketchStatus:
    def nome(cid):
        return sk.describe_constraint(cid, values.get(cid))

    if conflict:
        # le quote prima dei vincoli; l'ultima aggiunta è di solito quella "nuova"
        dims = sorted((c for c in conflict if c.startswith('D')), key=lambda c: int(c[1:]))
        altri = [c for c in conflict if c not in dims]
        nuova = dims[-1] if dims else altri[0]
        resto = [c for c in dims + altri if c != nuova]
        testo = f'{cap(nome(nuova))} è in conflitto con ' + (', '.join(nome(c) for c in resto) or 'altri vincoli') + \
                '. Togline una oppure cambia il valore.'
        return SketchStatus(OVER, dof, testo, conflicting=conflict, redundant=redundant)
    if redundant:
        if len(redundant) == 1:
            n = nome(redundant[0])
            testo = (f'{n[0].upper()}{n[1:]} non serve: la misura è già decisa dagli altri vincoli. '
                     'Toglila, altrimenti andrà in conflitto quando cambi le quote.')
        else:
            testo = ('Questi vincoli non servono, la geometria è già decisa dagli altri: '
                     + '; '.join(nome(c) for c in redundant) + '. Togline almeno uno.')
        return SketchStatus(REDUNDANT, dof, testo, redundant=redundant)
    if dof == 0:
        return SketchStatus(FULLY, 0, 'Lo sketch è completamente vincolato.')
    gradi = 'grado di libertà' if dof == 1 else 'gradi di libertà'
    return SketchStatus(UNDER, dof, f'Lo sketch ha ancora {dof} {gradi}: mancano quote o vincoli.')


def _result(sk, s, pid, lid, cid_, aid, status, values, solved: bool) -> SolvedSketch:
    pts = {}
    for k, g in pid.items():
        if solved:
            pts[k] = tuple(s.get_point(g))
        else:
            e = sk.entities[k]
            pts[k] = (e['x'], e['y'])
    circles = {}
    for k, g in cid_.items():
        e = sk.entities[k]
        circles[k] = (e['center'], s.get_circle(g).radius if solved else e['r'])
    arcs = {}
    for k, g in aid.items():
        e = sk.entities[k]
        if solved:
            r = s.get_arc(g).radius
        else:
            c, a = sk.entities[e['center']], sk.entities[e['start']]
            r = math.hypot(a['x'] - c['x'], a['y'] - c['y'])
        arcs[k] = (e['center'], e['start'], e['end'], r)
    lines = {k: (sk.entities[k]['a'], sk.entities[k]['b']) for k in lid}
    out = SolvedSketch(sk, pts, circles, arcs, lines, status, values)
    if solved:
        _check_degenerate(out)
    return out


def _check_degenerate(ss: SolvedSketch) -> None:
    for k, (a, b) in ss.lines.items():
        (x1, y1), (x2, y2) = ss.points[a], ss.points[b]
        if math.hypot(x2 - x1, y2 - y1) < TOL:
            raise SketchError(f'Con queste quote {ss.sketch.describe(k)} ha lunghezza zero.', code='sketch_degenere')
    for k, (_, r) in ss.circles.items():
        if r < TOL:
            raise SketchError(f'Con queste quote {ss.sketch.describe(k)} ha raggio zero.', code='sketch_degenere')
